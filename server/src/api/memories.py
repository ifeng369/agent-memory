"""
API 路由 - 记忆管理
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..database import get_db
from ..core.memory_service import get_memory_service
from ..models.memory import Memory
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["memories"])

# 同一服务端可被多个 Agent 共用；这些请求头决定记忆归属的项目/Agent/会话
SCOPE_HEADERS = {
    "project_id": "X-Project-Id",
    "agent_id": "X-Agent-Id",
    "session_id": "X-Session-Id",
}


def get_scope(request: Request) -> Dict[str, str]:
    """从请求头读取作用域，写入记忆 metadata 供检索过滤。"""
    return {
        key: value
        for key, header in SCOPE_HEADERS.items()
        if (value := request.headers.get(header))
    }


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    type: str = "long_term"
    importance: Optional[float] = Field(None, ge=0, le=1)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1)
    importance: Optional[float] = Field(None, ge=0, le=1)
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_memory(
    request: Request,
    payload: MemoryCreate,
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """创建新记忆"""
    try:
        memory = await memory_service.create_memory(
            content=payload.content,
            type=payload.type,
            importance=payload.importance,
            tags=payload.tags,
            metadata={**(payload.metadata or {}), **get_scope(request)},
            expires_at=payload.expires_at
        )
        return {
            "success": True,
            "data": memory.to_dict()
        }
    except Exception as e:
        logger.error(f"Create memory failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=Dict[str, Any])
async def list_memories(
    request: Request,
    type: Optional[str] = Query(None, description="记忆类型"),
    tags: Optional[str] = Query(None, description="标签过滤"),
    agent_id: Optional[str] = Query(None, description="Agent 过滤，留空为同项目全部 Agent"),
    include_expired: bool = Query(False, description="是否包含已过期记忆"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    order_by: str = Query("created_at", description="排序字段"),
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """查询记忆列表"""
    tag_list = tags.split(",") if tags else None
    scope = get_scope(request)
    
    memories = await memory_service.list_memories(
        type=type,
        tags=tag_list,
        limit=limit,
        offset=offset,
        order_by=order_by,
        project_id=scope.get("project_id"),
        agent_id=agent_id,
        include_expired=include_expired
    )
    
    return {
        "success": True,
        "data": [m.to_dict() for m in memories],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": len(memories)
        }
    }



@router.put("/{memory_id}", response_model=Dict[str, Any])
async def update_memory(
    request: Request,
    memory_id: str,
    payload: MemoryUpdate,
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """更新记忆"""
    metadata = {**(payload.metadata or {}), **get_scope(request)} if payload.metadata is not None else None
    memory = await memory_service.update_memory(
        memory_id=memory_id,
        content=payload.content,
        metadata=metadata,
        importance=payload.importance,
        tags=payload.tags
    )
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return {"success": True, "data": memory.to_dict()}


@router.delete("/{memory_id}", response_model=Dict[str, Any])
async def delete_memory(
    memory_id: str,
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """删除记忆"""
    success = await memory_service.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "message": "Memory deleted"}


@router.post("/search", response_model=Dict[str, Any])
async def search_memories(
    request: Request,
    query: str = Query(..., min_length=1, description="搜索查询"),
    type: Optional[str] = Query(None, description="记忆类型过滤"),
    agent_id: Optional[str] = Query(None, description="Agent 过滤，留空为同项目全部 Agent"),
    include_expired: bool = Query(False, description="是否包含已过期记忆"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    threshold: float = Query(0.7, ge=0, le=1, description="相似度阈值"),
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """语义搜索记忆"""
    scope = get_scope(request)
    results = await memory_service.search_memories(
        query=query,
        type=type,
        limit=limit,
        threshold=threshold,
        project_id=scope.get("project_id"),
        agent_id=agent_id,
        include_expired=include_expired
    )
    
    return {
        "success": True,
        "data": results,
        "query": query,
        "count": len(results)
    }


@router.get("/tags", response_model=Dict[str, Any])
async def get_tags(
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """获取所有标签"""
    tags = await memory_service.get_tags()
    return {
        "success": True,
        "data": [t.to_dict() for t in tags]
    }


@router.post("/compress", response_model=Dict[str, Any])
async def compress_memories(
    request: Request,
    memory_ids: List[str],
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """压缩多条记忆"""
    if len(memory_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 条记忆")
    
    compressed = await memory_service.compress_memories(memory_ids)
    if not compressed:
        raise HTTPException(status_code=500, detail="压缩失败")
    
    return {
        "success": True,
        "data": compressed.to_dict()
    }


@router.get("/stats", response_model=Dict[str, Any])
async def get_stats(
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """获取统计信息"""
    from sqlalchemy import func, select
    
    # 总数统计
    total_result = await db.execute(select(func.count()).select_from(Memory))
    total = total_result.scalar()
    
    # 按类型统计
    type_result = await db.execute(
        select(Memory.type, func.count()).group_by(Memory.type)
    )
    by_type = {row[0]: row[1] for row in type_result.fetchall()}
    
    return {
        "success": True,
        "data": {
            "total_memories": total,
            "by_type": by_type
        }
    }


@router.get("/{memory_id}", response_model=Dict[str, Any])
async def get_memory(
    memory_id: str,
    db = Depends(get_db),
    memory_service = Depends(get_memory_service)
):
    """获取单条记忆"""
    memory = await memory_service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "data": memory.to_dict()}
