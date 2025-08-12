"""
日志配置
基于 loguru，实现：
- 控制台彩色输出
- 多文件拆分（总日志、错误、HIS、WS、AI、DB、系统）
- 文件轮转、保留、压缩
- 模块级过滤，避免日志串扰
"""

import sys
import os
from typing import Callable
from loguru import logger
from app.core.config import settings


def _ensure_log_dir() -> str:
    log_dir = settings.LOG_DIR or "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    return log_dir


def _build_path(log_dir: str, name: str) -> str:
    return os.path.join(log_dir, name)


def _module_filter(module_prefixes: tuple[str, ...]) -> Callable[[dict], bool]:
    """返回一个过滤器：仅保留指定模块前缀的日志。
    说明：record["name"] 为 logger 记录中的模块名（python module 名）。
    """
    def _filter(record: dict) -> bool:
        name = record.get("name", "")
        return any(name.startswith(prefix) for prefix in module_prefixes)
    return _filter


def setup_logging():
    """设置全局日志：控制台 + 多文件拆分"""
    # 移除默认处理器
    logger.remove()

    log_dir = _ensure_log_dir()

    # 控制台输出（含调试信息，便于开发）
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    # 通用文件输出（汇总一份，便于统一排查）
    logger.add(
        _build_path(log_dir, "app_{time:YYYYMMDD}.log"),
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        encoding="utf-8",
        compression=settings.LOG_COMPRESSION,
    )

    # 错误专用
    logger.add(
        _build_path(log_dir, "error_{time:YYYYMMDD}.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        encoding="utf-8",
        compression=settings.LOG_COMPRESSION,
    )

    # 模块拆分：HIS / WebSocket / AI / DB / System
    modules = {
        "his": ("app.api.routes.his_push", "app.services.his_service"),
        "ws": ("app.api.routes.websocket_manager", "app.services.websocket_service"),
        "ai": ("app.services.ai_service",),
        "db": ("app.core.database", "app.models.database_models"),
        "system": ("app.core", "app.main"),
    }

    for tag, prefixes in modules.items():
        logger.add(
            _build_path(log_dir, f"{tag}_{{time:YYYYMMDD}}.log"),
            level=settings.LOG_LEVEL,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation=settings.LOG_ROTATION,
            retention=settings.LOG_RETENTION,
            encoding="utf-8",
            compression=settings.LOG_COMPRESSION,
            filter=_module_filter(prefixes),
        )

    logger.info("✅ 日志系统初始化完成（多文件拆分/轮转/压缩）")


def get_logger(name: str | None = None):
    """获取日志器实例；可绑定自定义 name 用于 filter 精确匹配。"""
    if name:
        return logger.bind(name=name)
    return logger