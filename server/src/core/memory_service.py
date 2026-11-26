"""
记忆管理服务
"""
from typing import List, Optional, Dict, Any
import asyncio
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, text, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from .embedding_service import embedding_service
from ..models.memory import Memory, MemoryRelation, Tag, MemoryTag, generate_hash
from ..database import get_db
from ..config import settings


class MemoryService:
    """记忆管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = embedding_service
    
    async def create_memory(
        self,
        content: str,
        type: str = "long_term",
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
        tags: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None
    ) -> Memory:
        """创建记忆"""
        # 带时区的 ISO 时间统一转成 UTC 朴素时间，匹配 TIMESTAMP WITHOUT TIME ZONE
        if expires_at is not None and expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        # 哈希带上项目：同一事实可在不同项目各存一份
        scope = metadata or {}
        content_hash = generate_hash(f"{scope.get('project_id', '')}\0{content}")
        
        # 检查是否已存在
        existing = await self.get_by_hash(content_hash)
        if existing:
            return existing
        
        # CPU 推理放到线程，避免阻塞事件循环
        embedding = await asyncio.to_thread(self.embedding_service.encode_single, content)
        
        # 创建记忆对象
        memory = Memory(
            content=content,
            content_hash=content_hash,
            embedding=embedding,
            type=type,
            extra=metadata or {},
            importance=importance if importance is not None else settings.DEFAULT_IMPORTANCE_THRESHOLD,
            expires_at=expires_at,
        )
        
        self.db.add(memory)
        await self.db.flush()
        
        # 添加标签
        if tags:
            await self._add_tags(memory.id, tags)
        
        await self.db.commit()
        await self.db.refresh(memory)
        
        return memory
    
    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单条记忆"""
        result = await self.db.execute(
            select(Memory)
            .where(Memory.id == memory_id)
            .options(selectinload(Memory.tags))
        )
        memory = result.scalar_one_or_none()
        
        if memory:
            # 更新访问统计
            await self._update_access(memory_id)
        
        return memory
    
    async def get_by_hash(self, content_hash: str) -> Optional[Memory]:
        """根据哈希获取记忆"""
        result = await self.db.execute(
            select(Memory).where(Memory.content_hash == content_hash)
        )
        return result.scalar_one_or_none()
    
    async def list_memories(
        self,
        type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "created_at",
        desc: bool = True,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        include_expired: bool = False
    ) -> List[Memory]:
        """查询记忆列表"""
        query = select(Memory).options(selectinload(Memory.tags))
        
        if type:
            query = query.where(Memory.type == type)
        
        if project_id:
            query = query.where(Memory.extra["project_id"].astext == project_id)
        if agent_id:
            query = query.where(Memory.extra["agent_id"].astext == agent_id)
        if not include_expired:
            query = query.where(or_(Memory.expires_at.is_(None), Memory.expires_at > func.now()))
        
        if tags:
            # 根据标签筛选
            tag_subquery = (
                select(MemoryTag.memory_id)
                .join(Tag)
                .where(Tag.name.in_(tags))
                .group_by(MemoryTag.memory_id)
                .having(func.count() == len(tags))
            )
            query = query.where(Memory.id.in_(tag_subquery))
        
        # 排序
        order_column = getattr(Memory, order_by, Memory.created_at)
        if desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
        
        # 分页
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        memories = result.scalars().all()
        
        return memories
    
    async def search_memories(
        self,
        query: str,
        type: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.7,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """语义搜索记忆（同项目跨 Agent 共享，默认排除过期项）"""
        query_embedding = await asyncio.to_thread(self.embedding_service.encode_single, query)
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        sql = text("""
            SELECT id, type, content, metadata, importance,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity,
                   CASE WHEN content ILIKE :keyword THEN 0.05 ELSE 0 END AS keyword_boost,
                   created_at, updated_at
            FROM memories
            WHERE 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
            AND (CAST(:type_filter AS varchar) IS NULL OR type = :type_filter)
            AND (CAST(:project_id AS varchar) IS NULL OR metadata->>'project_id' = :project_id)
            AND (CAST(:agent_id AS varchar) IS NULL OR metadata->>'agent_id' = :agent_id)
            AND (:include_expired OR expires_at IS NULL OR expires_at > now())
            ORDER BY (1 - (embedding <=> CAST(:embedding AS vector)))
                     + (CASE WHEN content ILIKE :keyword THEN 0.05 ELSE 0 END) DESC
            LIMIT :limit
        """)
        
        result = await self.db.execute(
            sql,
            {
                "embedding": embedding_str, "threshold": threshold, "type_filter": type,
                "project_id": project_id, "agent_id": agent_id, "include_expired": include_expired,
                "keyword": f"%{query}%", "limit": limit,
            }
        )
        
        rows = result.fetchall()
        
        return [
            {
                "id": row.id,
                "type": row.type,
                "content": row.content,
                "metadata": row.metadata,
                "importance": row.importance,
                "similarity": float(row.similarity),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
    
    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Memory]:
        """更新记忆"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return None
        
        if metadata is not None:
            memory.extra = metadata
        
        if content:
            memory.content = content
            # 哈希与 create 保持一致：带项目前缀，避免跨项目去重误判
            project_id = (memory.extra or {}).get("project_id", "")
            memory.content_hash = generate_hash(f"{project_id}\0{content}")
            memory.embedding = await asyncio.to_thread(self.embedding_service.encode_single, content)
        
        if importance is not None:
            memory.importance = importance
        
        if tags is not None:
            # 清空旧标签
            await self.db.execute(
                delete(MemoryTag).where(MemoryTag.memory_id == memory_id)
            )
            # 添加新标签
            await self._add_tags(memory_id, tags)
        
        memory.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(memory)
        
        return memory
    
    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        result = await self.db.execute(
            delete(Memory).where(Memory.id == memory_id)
        )
        await self.db.commit()
        return result.rowcount > 0
    
    async def _add_tags(self, memory_id: str, tag_names: List[str]):
        """添加标签到记忆"""
        for tag_name in tag_names:
            # 查找或创建标签
            tag = await self.db.execute(
                select(Tag).where(Tag.name == tag_name)
            )
            tag = tag.scalar_one_or_none()
            
            if not tag:
                tag = Tag(name=tag_name)
                self.db.add(tag)
                await self.db.flush()
            
            # 创建关联
            memory_tag = MemoryTag(memory_id=memory_id, tag_id=tag.id)
            self.db.add(memory_tag)
    
    async def _update_access(self, memory_id: str):
        """更新访问统计"""
        await self.db.execute(
            update(Memory)
            .where(Memory.id == memory_id)
            .values(
                access_count=Memory.access_count + 1,
                last_accessed=func.now()
            ),
            execution_options={"synchronize_session": False}
        )
        # 不在这里 commit，交给 get_db 在请求结束时统一提交
    
    async def get_tags(self) -> List[Tag]:
        """获取所有标签"""
        result = await self.db.execute(select(Tag).order_by(Tag.name))
        return result.scalars().all()
    
    async def create_relation(
        self,
        from_memory_id: str,
        to_memory_id: str,
        relation_type: str,
        strength: float = 1.0
    ) -> MemoryRelation:
        """创建记忆关联"""
        relation = MemoryRelation(
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
            relation_type=relation_type,
            strength=strength
        )
        self.db.add(relation)
        await self.db.commit()
        await self.db.refresh(relation)
        return relation
    
    async def compress_memories(self, memory_ids: List[str]) -> Optional[Memory]:
        """压缩多条记忆为一条 (简单实现：合并内容)"""
        memories = []
        for mid in memory_ids:
            memory = await self.get_memory(mid)
            if memory:
                memories.append(memory)
        
        if len(memories) < 2:
            return None
        
        # 合并内容
        combined_content = "\n\n".join([m.content for m in memories])
        
        # 计算平均重要性
        avg_importance = sum(m.importance for m in memories) / len(memories)
        
        # 创建压缩记忆
        compressed = await self.create_memory(
            content=combined_content,
            type="compressed",
            metadata={
                **(memories[0].extra or {}),
                "compressed_from": memory_ids,
                "original_count": len(memories)
            },
            importance=avg_importance
        )
        
        # 创建关联
        for memory in memories:
            await self.create_relation(
                from_memory_id=compressed.id,
                to_memory_id=memory.id,
                relation_type="compressed_from"
            )
        
        return compressed


# 依赖注入
def get_memory_service(db = Depends(get_db)) -> MemoryService:
    return MemoryService(db)
