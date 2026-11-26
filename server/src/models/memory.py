"""
数据模型定义
"""
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression
from ..database import Base
import uuid
import hashlib
from datetime import datetime


def generate_id(prefix: str = "") -> str:
    """生成唯一 ID"""
    uid = uuid.uuid4().hex[:16]
    return f"{prefix}{uid}" if prefix else uid


def generate_hash(content: str) -> str:
    """生成内容哈希"""
    return hashlib.sha256(content.encode()).hexdigest()


class Memory(Base):
    """记忆模型"""
    __tablename__ = "memories"
    
    id = Column(String(64), primary_key=True, default=lambda: generate_id("mem_"))
    type = Column(String(32), nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), unique=True)
    embedding = Column(Vector(512))
    importance = Column(Float, default=0.5)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=True, index=True)
    extra = Column("metadata", JSONB, default=dict)  # SQLAlchemy 保留 metadata 属性名
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 关联关系
    relations_from = relationship("MemoryRelation", foreign_keys="MemoryRelation.from_memory_id", back_populates="from_memory", cascade="all, delete-orphan")
    relations_to = relationship("MemoryRelation", foreign_keys="MemoryRelation.to_memory_id", back_populates="to_memory", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="memory_tags", back_populates="memories")
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.extra,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MemoryRelation(Base):
    """记忆关联模型"""
    __tablename__ = "memory_relations"
    
    id = Column(String(64), primary_key=True, default=generate_id)
    from_memory_id = Column(String(64), ForeignKey("memories.id", ondelete="CASCADE"), index=True)
    to_memory_id = Column(String(64), ForeignKey("memories.id", ondelete="CASCADE"), index=True)
    relation_type = Column(String(32))
    strength = Column(Float, default=1.0)
    created_at = Column(DateTime, default=func.now())
    
    from_memory = relationship("Memory", foreign_keys=[from_memory_id], back_populates="relations_from")
    to_memory = relationship("Memory", foreign_keys=[to_memory_id], back_populates="relations_to")


class Tag(Base):
    """标签模型"""
    __tablename__ = "tags"
    
    id = Column(String(64), primary_key=True, default=generate_id)
    name = Column(String(128), unique=True, nullable=False)
    color = Column(String(7))
    created_at = Column(DateTime, default=func.now())
    
    memories = relationship("Memory", secondary="memory_tags", back_populates="tags")
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemoryTag(Base):
    """记忆 - 标签关联表"""
    __tablename__ = "memory_tags"
    
    memory_id = Column(String(64), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(String(64), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, default=func.now())

