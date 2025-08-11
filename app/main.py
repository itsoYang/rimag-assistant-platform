"""
助手管理端中间件 - FastAPI应用入口
MVP阶段实施：HIS接口接收、WebSocket管理、AI服务代理、调用链日志
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from app.core.config import settings
from app.core.database import init_database
from app.api.routes import his_push, ai_proxy, websocket_manager
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("🚀 启动助手管理端中间件...")
    
    # 设置日志
    setup_logging()
    
    # 初始化数据库
    await init_database()
    
    logger.info("✅ 助手管理端中间件启动完成")
    
    yield
    
    # 关闭时清理
    logger.info("🔄 关闭助手管理端中间件...")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    
    app = FastAPI(
        title="助手管理端中间件",
        description="HIS、客户端、AI服务之间的中间件服务 - MVP阶段",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(his_push.router, prefix="/api", tags=["HIS推送接口"])
    app.include_router(ai_proxy.router, prefix="/api", tags=["AI服务代理"])
    app.include_router(websocket_manager.router, prefix="/ws", tags=["WebSocket连接"])
    
    # 健康检查
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "assistant-management-platform"}
    
    return app


# 创建应用实例
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )