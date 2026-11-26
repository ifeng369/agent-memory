"""
主应用入口
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import time
import logging

from .config import settings
from .database import engine, Base
from .core.embedding_service import embedding_service
from .api import memories

# 配置日志
logging.basicConfig(
    format="%(levelname)s: %(message)s",
    level=getattr(logging, settings.LOG_LEVEL)
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("Starting Memory System...")
    
    # 初始化数据库
    logger.info("Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 初始化向量模型
    logger.info("Loading embedding model...")
    embedding_service.initialize()
    
    logger.info(f"Memory System started on port {settings.PORT}")
    
    yield
    
    # 关闭时清理
    logger.info("Shutting down Memory System...")
    await engine.dispose()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="分布式记忆系统 - 支持 OpenCode 及其他 Agent 框架",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s"
    )
    return response


# 认证中间件 (简化版)
@app.middleware("http")
async def authenticate(request: Request, call_next):
    # 跳过健康检查和文档
    if request.url.path in ["/api/health", "/docs", "/redoc", "/openapi.json", "/web"]:
        return await call_next(request)
    
    # 获取 API Key
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
    
    # 使用默认占位密钥时放行本地开发；换成真实密钥后强制校验
    if settings.API_SECRET != "your-secret-key-change-in-production" and api_key != settings.API_SECRET:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid API Key"}
        )
    
    return await call_next(request)


# 全局异常处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error"
        }
    )


# 注册路由
app.include_router(memories.router, prefix=settings.API_PREFIX)


# 健康检查
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "model": settings.MODEL_NAME
    }


# Web 管理台（根路径与 /web 均返回同一页面）
WEB_INDEX = Path(__file__).parent.parent / "web" / "index.html"


@app.get("/", include_in_schema=False)
async def web_ui():
    return FileResponse(WEB_INDEX)


@app.get("/web", include_in_schema=False)
async def web_ui_alias():
    return FileResponse(WEB_INDEX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
