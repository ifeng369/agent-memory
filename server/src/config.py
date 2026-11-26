"""
记忆系统 - 配置管理
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""
    
    # 服务配置
    APP_NAME: str = "agent-memory"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 3000
    
    # 数据库配置
    DATABASE_URL: str = "postgresql+asyncpg://memory_user:memory_pass@localhost:5432/memory"
    
    # API 配置
    API_SECRET: str = "your-secret-key-change-in-production"
    API_PREFIX: str = "/api/v1"
    
    # 向量模型配置
    MODEL_NAME: str = "/app/models/agent-memory-onnx"
    MODEL_DIMENSION: int = 512
    BATCH_SIZE: int = 32
    
    # 性能配置
    OMP_NUM_THREADS: int = 4
    MKL_NUM_THREADS: int = 4
    
    # 记忆配置
    DEFAULT_IMPORTANCE_THRESHOLD: float = 0.5
    FORGETTING_DAYS: int = 90  # 低重要性记忆过期天数
    COMPRESSION_THRESHOLD: int = 100  # 触发压缩的记忆数量
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()
