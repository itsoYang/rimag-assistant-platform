"""
配置管理
支持环境变量配置和默认值
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用基础配置
    APP_NAME: str = "助手管理端中间件"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS配置 - 简化版本，直接从.env读取
    ALLOWED_ORIGINS: str = '["http://localhost:3000","http://localhost:8080","http://localhost:63342","http://127.0.0.1:3000","http://127.0.0.1:8080","http://127.0.0.1:63342","file://","null","*"]'
    
    # MySQL数据库配置
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "password"
    MYSQL_DATABASE: str = "assistant_management"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
    
    # HIS推送接口配置
    HIS_SERVICE_ID: str = "CHKR01"
    HIS_SCENE_TYPE: str = "EXAM001"
    HIS_EXTEND_SUB_ID: str = "AI_REC"
    
    # 外部AI服务配置
    AI_SERVICE_BASE_URL: str = "http://210.12.11.251:27860"
    AI_SERVICE_ENDPOINT: str = "/rimagai/checkitem/recommend_item_with_reason"
    AI_SERVICE_TIMEOUT: int = 30
    AI_DEFAULT_RECOMMEND_COUNT: int = 3
    AI_DEFAULT_SOURCE: str = "lip"
    
    # WebSocket配置
    WS_HEARTBEAT_INTERVAL: int = 30  # 秒
    WS_HEARTBEAT_TIMEOUT: int = 10   # 秒
    WS_MAX_RECONNECT_ATTEMPTS: int = 5
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_RETENTION: str = "30 days"
    LOG_ROTATION: str = "100 MB"
    LOG_DIR: str = "logs"               # 日志目录
    LOG_COMPRESSION: str = "zip"         # 可选："zip" | "gz" | None
    
    # JWT认证配置（预留）
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 数据库初始化策略
    AUTO_CREATE_TABLES: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局设置实例
settings = Settings()

# 调试：输出当前加载的ALLOWED_ORIGINS配置
from loguru import logger
logger.info(f"🔧 当前ALLOWED_ORIGINS配置: {settings.ALLOWED_ORIGINS}")