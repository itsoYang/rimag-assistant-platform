"""
调用链追踪服务：创建 Trace 与 Span，记录开始/结束与属性
"""

from typing import Optional, Dict
from uuid import uuid4
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import TraceRecord, SpanRecord, uuid7_str


def _now() -> datetime:
    return datetime.now()


def generate_trace_id() -> str:
    return uuid7_str()


async def create_trace(db: AsyncSession, request_id: Optional[str], client_id: Optional[str]) -> str:
    """创建新的追踪记录"""
    trace_id = generate_trace_id()
    try:
        # 直接使用传入的db会话，不创建新的事务上下文
        rec = TraceRecord(
            trace_id=trace_id,
            patient_id=None,
            hospital_id=None,
            start_time=_now(),
            end_time=None,
            status="RUNNING",
            total_duration_ms=0,
        )
        db.add(rec)
        await db.flush()  # 使用flush与外层事务兼容
        return trace_id
    except Exception as e:
        # 记录错误但不阻断流程
        print(f"创建追踪记录失败: {e}")
        return trace_id


async def create_span(
    db: AsyncSession,
    trace_id: str,
    name: str,
    status: str = "RUNNING",
    attributes: Optional[Dict] = None,
    parent_span_id: Optional[str] = None,
    service_name: str = "Assistant-Server",
    api_path: Optional[str] = None,
    client_id: Optional[str] = None,
) -> str:
    """创建新的Span记录"""
    span_id = uuid7_str()
    try:
        # 直接使用传入的db会话，不创建新的事务上下文
        span = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            service_name=service_name,
            span_name=name,
            start_time=_now(),
            end_time=None,  # 创建时不设置结束时间
            duration_ms=0,
            status=status,
            request_data=attributes if attributes else None,
            response_data=None,
            error_message=None,
            client_id=client_id,
            api_path=api_path,
        )
        db.add(span)
        await db.flush()  # 使用flush与外层事务兼容
        return span_id
    except Exception as e:
        print(f"创建Span记录失败: {e}")
        # 返回临时ID以避免阻断流程
        return span_id


async def finish_span(
    db: AsyncSession,
    span_id: str,
    status: str = "SUCCESS",
    response: Optional[Dict] = None,
    error_message: Optional[str] = None,
) -> None:
    """结束Span记录并计算持续时间"""
    try:
        # 直接使用传入的db会话，不创建新的事务上下文
        row = (
            await db.execute(select(SpanRecord).where(SpanRecord.span_id == span_id))
        ).scalar_one_or_none()
        if not row:
            print(f"未找到Span记录: {span_id}")
            return
        
        end = _now()
        row.end_time = end
        # 计算持续时间（毫秒）
        if row.start_time:
            row.duration_ms = int((end - row.start_time).total_seconds() * 1000)
        else:
            row.duration_ms = 0
        
        row.status = status
        if response is not None:
            row.response_data = response
        if error_message:
            row.error_message = error_message
        
        await db.flush()  # 使用flush与外层事务兼容
    except Exception as e:
        print(f"结束Span记录失败: {e}")


async def finish_trace(
    db: AsyncSession,
    trace_id: str,
    status: str = "SUCCESS",
    error_message: Optional[str] = None,
) -> None:
    """结束追踪记录并计算总持续时间"""
    try:
        # 直接使用传入的db会话，不创建新的事务上下文
        row = (
            await db.execute(select(TraceRecord).where(TraceRecord.trace_id == trace_id))
        ).scalar_one_or_none()
        if not row:
            print(f"未找到追踪记录: {trace_id}")
            return
        
        end = _now()
        row.end_time = end
        # 计算总持续时间（毫秒）
        if row.start_time:
            row.total_duration_ms = int((end - row.start_time).total_seconds() * 1000)
        else:
            row.total_duration_ms = 0
        
        row.status = status
        
        # 确保数据持久化到数据库
        await db.commit()
    except Exception as e:
        print(f"结束追踪记录失败: {e}")
        # 发生异常时回滚事务
        await db.rollback()
        raise


