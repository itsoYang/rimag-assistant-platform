"""全链路调用追踪系统
实现Trace ID生成、传递、管理和存储功能
"""

import uuid
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
import json
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database_models import TraceRecord, SpanRecord


class SpanType(str, Enum):
    """调用片段类型"""
    HTTP_REQUEST = "http_request"
    AI_SERVICE = "ai_service"
    DATABASE = "database"
    WEBSOCKET = "websocket"
    EXTERNAL_API = "external_api"
    BUSINESS_LOGIC = "business_logic"


class TraceStatus(str, Enum):
    """调用链状态"""
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class SpanInfo:
    """调用片段信息"""
    span_id: str
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    span_type: SpanType = SpanType.BUSINESS_LOGIC
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: TraceStatus = TraceStatus.RUNNING
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None

    def finish(self, status: TraceStatus = TraceStatus.SUCCESS, error_message: Optional[str] = None):
        """结束Span"""
        self.end_time = datetime.now()
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.status = status
        if error_message:
            self.error_message = error_message

    def add_tag(self, key: str, value: Any):
        """添加标签"""
        self.tags[key] = value

    def add_log(self, message: str, level: str = "info", **kwargs):
        """添加日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs
        }
        self.logs.append(log_entry)


@dataclass
class TraceInfo:
    """调用链信息"""
    trace_id: str
    root_span_id: str
    service_name: str = "rimag-assistant-platform"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: TraceStatus = TraceStatus.RUNNING
    spans: Dict[str, SpanInfo] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, status: TraceStatus = TraceStatus.SUCCESS):
        """结束Trace"""
        self.end_time = datetime.now()
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.status = status

    def add_span(self, span: SpanInfo):
        """添加Span"""
        self.spans[span.span_id] = span

    def get_span(self, span_id: str) -> Optional[SpanInfo]:
        """获取Span"""
        return self.spans.get(span_id)


# 上下文变量，用于在异步环境中传递Trace信息
_current_trace: ContextVar[Optional[TraceInfo]] = ContextVar('current_trace', default=None)
_current_span: ContextVar[Optional[SpanInfo]] = ContextVar('current_span', default=None)


class TraceManager:
    """调用链管理器"""

    @staticmethod
    def generate_trace_id() -> str:
        """生成Trace ID"""
        timestamp = int(time.time() * 1000)
        random_part = str(uuid.uuid4()).replace('-', '')[:16]
        return f"trace_{timestamp}_{random_part}"

    @staticmethod
    def generate_span_id() -> str:
        """生成Span ID"""
        return f"span_{str(uuid.uuid4()).replace('-', '')[:16]}"

    @classmethod
    def start_trace(
        cls,
        operation_name: str,
        trace_id: Optional[str] = None,
        service_name: str = "rimag-assistant-platform",
        **metadata
    ) -> TraceInfo:
        """开始新的调用链"""
        if not trace_id:
            trace_id = cls.generate_trace_id()
        
        root_span_id = cls.generate_span_id()
        
        # 创建Trace信息
        trace_info = TraceInfo(
            trace_id=trace_id,
            root_span_id=root_span_id,
            service_name=service_name,
            metadata=metadata
        )
        
        # 创建根Span
        root_span = SpanInfo(
            span_id=root_span_id,
            operation_name=operation_name,
            span_type=SpanType.BUSINESS_LOGIC
        )
        
        trace_info.add_span(root_span)
        
        # 设置到上下文
        _current_trace.set(trace_info)
        _current_span.set(root_span)
        
        logger.bind(trace_id=trace_id, span_id=root_span_id).info(
            f"🔍 开始调用链: {operation_name}"
        )
        
        return trace_info

    @classmethod
    def start_span(
        cls,
        operation_name: str,
        span_type: SpanType = SpanType.BUSINESS_LOGIC,
        parent_span_id: Optional[str] = None,
        **tags
    ) -> Optional[SpanInfo]:
        """开始新的调用片段"""
        current_trace = _current_trace.get()
        if not current_trace:
            logger.warning("⚠️ 没有活跃的调用链，无法创建Span")
            return None
        
        # 确定父Span ID
        if not parent_span_id:
            current_span = _current_span.get()
            parent_span_id = current_span.span_id if current_span else current_trace.root_span_id
        
        # 创建新Span
        span_id = cls.generate_span_id()
        span = SpanInfo(
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            span_type=span_type,
            tags=tags
        )
        
        # 添加到Trace
        current_trace.add_span(span)
        
        # 设置为当前Span
        _current_span.set(span)
        
        logger.bind(
            trace_id=current_trace.trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id
        ).info(f"📍 开始调用片段: {operation_name}")
        
        return span

    @classmethod
    def finish_span(
        cls,
        span: Optional[SpanInfo] = None,
        status: TraceStatus = TraceStatus.SUCCESS,
        error_message: Optional[str] = None
    ):
        """结束调用片段"""
        if not span:
            span = _current_span.get()
        
        if not span:
            logger.warning("⚠️ 没有活跃的Span可以结束")
            return
        
        span.finish(status, error_message)
        
        logger.bind(
            trace_id=cls.get_current_trace_id(),
            span_id=span.span_id
        ).info(f"✅ 结束调用片段: {span.operation_name}, 耗时: {span.duration_ms}ms")

    @classmethod
    def finish_trace(
        cls,
        trace: Optional[TraceInfo] = None,
        status: TraceStatus = TraceStatus.SUCCESS
    ):
        """结束调用链"""
        if not trace:
            trace = _current_trace.get()
        
        if not trace:
            logger.warning("⚠️ 没有活跃的调用链可以结束")
            return
        
        # 结束所有未结束的Span
        for span in trace.spans.values():
            if span.status == TraceStatus.RUNNING:
                span.finish(status)
        
        # 结束Trace
        trace.finish(status)
        
        logger.bind(trace_id=trace.trace_id).info(
            f"🏁 结束调用链, 总耗时: {trace.duration_ms}ms, 状态: {status.value}"
        )
        
        # 清理上下文
        _current_trace.set(None)
        _current_span.set(None)

    @classmethod
    def get_current_trace(self) -> Optional[TraceInfo]:
        """获取当前调用链"""
        return _current_trace.get()

    @classmethod
    def get_current_span(self) -> Optional[SpanInfo]:
        """获取当前调用片段"""
        return _current_span.get()

    @classmethod
    def get_current_trace_id(self) -> Optional[str]:
        """获取当前Trace ID"""
        trace = _current_trace.get()
        return trace.trace_id if trace else None

    @classmethod
    def get_current_span_id(self) -> Optional[str]:
        """获取当前Span ID"""
        span = _current_span.get()
        return span.span_id if span else None

    @classmethod
    def add_tag(cls, key: str, value: Any, span: Optional[SpanInfo] = None):
        """添加标签到当前或指定Span"""
        if not span:
            span = _current_span.get()
        
        if span:
            span.add_tag(key, value)

    @classmethod
    def add_log(cls, message: str, level: str = "info", span: Optional[SpanInfo] = None, **kwargs):
        """添加日志到当前或指定Span"""
        if not span:
            span = _current_span.get()
        
        if span:
            span.add_log(message, level, **kwargs)

    @classmethod
    async def save_trace_to_db(cls, db: AsyncSession, trace: Optional[TraceInfo] = None):
        """保存调用链到数据库"""
        if not trace:
            trace = _current_trace.get()
        
        if not trace:
            logger.warning("⚠️ 没有调用链可以保存")
            return
        
        try:
            # 保存Trace记录
            trace_record = TraceRecord(
                trace_id=trace.trace_id,
                service_name=trace.service_name,
                start_time=trace.start_time,
                end_time=trace.end_time,
                duration_ms=trace.duration_ms,
                status=trace.status.value,
                metadata=json.dumps(trace.metadata, ensure_ascii=False)
            )
            db.add(trace_record)
            
            # 保存Span记录
            for span in trace.spans.values():
                span_record = SpanRecord(
                    trace_id=trace.trace_id,
                    span_id=span.span_id,
                    parent_span_id=span.parent_span_id,
                    operation_name=span.operation_name,
                    span_type=span.span_type.value,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    duration_ms=span.duration_ms,
                    status=span.status.value,
                    tags=json.dumps(span.tags, ensure_ascii=False) if span.tags else None,
                    logs=json.dumps(span.logs, ensure_ascii=False) if span.logs else None,
                    error_message=span.error_message
                )
                db.add(span_record)
            
            await db.commit()
            
            logger.bind(trace_id=trace.trace_id).info(
                f"💾 调用链已保存到数据库, Spans数量: {len(trace.spans)}"
            )
            
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ 保存调用链到数据库失败: {str(e)}")
            raise


class TraceContext:
    """调用链上下文管理器"""
    
    def __init__(
        self,
        operation_name: str,
        span_type: SpanType = SpanType.BUSINESS_LOGIC,
        trace_id: Optional[str] = None,
        **tags
    ):
        self.operation_name = operation_name
        self.span_type = span_type
        self.trace_id = trace_id
        self.tags = tags
        self.span: Optional[SpanInfo] = None
        self.is_root = False
    
    def __enter__(self) -> SpanInfo:
        # 检查是否已有活跃的调用链
        current_trace = TraceManager.get_current_trace()
        
        if not current_trace:
            # 创建新的调用链
            trace = TraceManager.start_trace(
                self.operation_name,
                self.trace_id,
                **self.tags
            )
            self.span = trace.get_span(trace.root_span_id)
            self.is_root = True
        else:
            # 创建子Span
            self.span = TraceManager.start_span(
                self.operation_name,
                self.span_type,
                **self.tags
            )
        
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            status = TraceStatus.ERROR if exc_type else TraceStatus.SUCCESS
            error_message = str(exc_val) if exc_val else None
            
            if self.is_root:
                TraceManager.finish_trace(status=status)
            else:
                TraceManager.finish_span(self.span, status, error_message)


# 装饰器支持
def trace_function(operation_name: Optional[str] = None, span_type: SpanType = SpanType.BUSINESS_LOGIC):
    """函数调用追踪装饰器"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            with TraceContext(op_name, span_type):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            with TraceContext(op_name, span_type):
                return func(*args, **kwargs)
        
        # 根据函数类型返回对应的包装器
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator