"""
数据库配置和连接管理
SQLAlchemy + MySQL
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from loguru import logger
from app.core.config import settings


class Base(DeclarativeBase):
    """数据库模型基类"""
    pass


# 数据库引擎
engine = create_async_engine(
    settings.DATABASE_URL.replace("mysql+pymysql://", "mysql+aiomysql://"),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600
)

# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_database():
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库会话错误: {e}")
            raise
        finally:
            await session.close()


async def init_database():
    """初始化数据库"""
    try:
        # 打印当前配置用于调试
        from app.core.config import settings
        logger.info(f"🔧 数据库配置: {settings.MYSQL_USER}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}")
        
        # 测试数据库连接
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ 数据库初始化完成")
        
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise


async def close_database():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("🔄 数据库连接已关闭")