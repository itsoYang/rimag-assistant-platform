"""
调用链追踪服务：创建 Trace 与 Span，记录开始/结束与属性
"""

from typing import Optional, Dict
from uuid import uuid4
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import TraceRecord, SpanRecord


def _now() -> datetime:
    return datetime.now()


def generate_trace_id() -> str:
    return f"{uuid4()}"


async def create_trace(db: AsyncSession, request_id: Optional[str], client_id: Optional[str]) -> str:
    trace_id = generate_trace_id()
    # 临时跳过数据库操作，确保核心流程顺畅运行
    # TODO: 修复数据库表结构后恢复此功能
    # rec = TraceRecord(
    #     trace_id=trace_id,
    #     patient_id=None,
    #     hospital_id=None,
    #     start_time=_now(),
    #     end_time=None,
    #     status="SUCCESS",
    #     total_duration_ms=0,
    # )
    # db.add(rec)
    # await db.commit()
    return trace_id


async def create_span(
    db: AsyncSession,
    trace_id: str,
    name: str,
    status: str = "running",
    attributes: Optional[Dict] = None,
    parent_span_id: Optional[str] = None,
    service_name: str = "Assistant-Server",
    api_path: Optional[str] = None,
) -> str:
    import json
    now = _now()
    span = SpanRecord(
        span_id=str(uuid4()),
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        service_name=service_name,
        span_name=name,
        start_time=now,
        end_time=now,
        duration_ms=0,
        status=status,
        request_data=None,
        response_data=None,
        error_message=None,
        client_id=None,
        api_path=api_path,
    )
    if attributes:
        span.request_data = attributes
    db.add(span)
    await db.commit()
    await db.refresh(span)
    return span.span_id  # type: ignore


async def finish_span(
    db: AsyncSession,
    span_id: str,
    status: str = "SUCCESS",
    response: Optional[Dict] = None,
    error_message: Optional[str] = None,
) -> None:
    import json
    row = (
        await db.execute(select(SpanRecord).where(SpanRecord.span_id == span_id))
    ).scalar_one_or_none()
    if not row:
        return
    end = _now()
    row.end_time = end
    row.duration_ms = int((end - row.start_time).total_seconds() * 1000)
    row.status = status
    if response is not None:
        row.response_data = response
    if error_message:
        row.error_message = error_message
    await db.commit()


