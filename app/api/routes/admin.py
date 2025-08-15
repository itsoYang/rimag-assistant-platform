"""
管理端接口
1) 客户端 & 日志分页查询（已有）
2) 服务治理（服务/端点 CRUD + 测试连接）
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_database
from app.models.database_models import (
    AiRecommendationLog,
    ClientInfo,
    HisPushLog,
    SystemLog,
    Service,
    ServiceInterface,
    RoleInfo,
    RoleServiceAcl,
    ClientRoleBinding,
    TraceRecord,
    SpanRecord,
)
from sqlalchemy import desc
from app.schemas.admin_schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceOut,
    ServiceEndpointCreate,
    ServiceEndpointUpdate,
    ServiceEndpointOut,
    TestConnectionResult,
    RoleCreate,
    RoleUpdate,
    RoleOut,
    RoleAclCreate,
    RoleAclOut,
    ClientRoleBindCreate,
    ClientRoleBindOut,
)
import httpx


router = APIRouter()
# ================= 字典管理 =================


@router.get("/dict")
async def list_dict(
    db: AsyncSession = Depends(get_database),
    dict_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500),
):
    from app.models.database_models import SysDict  # type: ignore
    from sqlalchemy import select as _select

    stmt = _select(SysDict)
    if dict_type:
        stmt = stmt.where(SysDict.dict_type == dict_type)
    stmt = stmt.order_by(desc(SysDict.sort_order), SysDict.create_time.desc())

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))).scalars().all()

    def _fmt_dt(dt) -> Optional[str]:
        return dt.isoformat(sep=" ", timespec="seconds") if dt else None

    items = [
        {
            "id": it.id,
            "dict_type": it.dict_type,
            "dict_key": it.dict_key,
            "dict_value": it.dict_value,
            "description": it.description,
            "sort_order": it.sort_order,
            "enabled": bool(it.enabled),
            "create_time": _fmt_dt(it.create_time),
            "update_time": _fmt_dt(it.update_time),
        }
        for it in rows
    ]

    return {"items": items, "total": total}


def _page_offset(page: int, page_size: int) -> int:
    return max(page - 1, 0) * page_size


@router.get("/clients")
async def list_clients(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    doctor_id: Optional[str] = None,
    client_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="connected|disconnected|unknown"),
):
    """分页查询客户端连接信息"""
    logger.bind(name="app.api.routes.admin").info(
        f"[ADMIN] list_clients page={page} pageSize={pageSize} doctor_id={doctor_id} client_id={client_id} status={status}"
    )

    conditions = []
    # doctor_id 字段在新表中不再维护，这里忽略筛选（保留形参兼容请求）
    if client_id:
        conditions.append(ClientInfo.client_id == client_id)
    if status in ("connected", "disconnected"):
        conditions.append(ClientInfo.connected == (status == "connected"))

    stmt = select(ClientInfo)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(ClientInfo.last_active.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(total_stmt)
    total = total_res.scalar_one()

    rows_res = await db.execute(
        stmt.offset(_page_offset(page, pageSize)).limit(pageSize)
    )
    items: List[ClientInfo] = rows_res.scalars().all()

    def _fmt_dt(dt) -> Optional[str]:
        return dt.isoformat(sep=" ", timespec="seconds") if dt else None

    data = [
        {
            "client_id": it.client_id,
            "doctor_id": None,
            "ip_address": it.ip_address,
            "connection_status": ("connected" if it.connected else "disconnected"),
            "disabled": (not it.enabled),
            "connected_at": _fmt_dt(it.connected_at),
            "last_heartbeat": _fmt_dt(it.last_active),
        }
        for it in items
    ]

    return {"items": data, "total": total}


@router.post("/clients/{client_id}/disconnect")
async def force_disconnect_client(client_id: str):
    """强制断开客户端连接（仅影响当前WS会话，不改变禁用状态）"""
    try:
        from app.services.websocket_service import websocket_manager
        await websocket_manager.disconnect(client_id, "admin_force_disconnect")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clients/{client_id}/disable")
async def disable_client(client_id: str, disabled: bool = Query(True), db: AsyncSession = Depends(get_database)):
    """启/禁用客户端（禁用后拒绝连接与调用）"""
    row = (await db.execute(select(ClientInfo).where(ClientInfo.client_id == client_id))).scalar_one_or_none()
    if not row:
        row = ClientInfo(client_id=client_id, enabled=not bool(disabled))
        db.add(row)
        await db.flush()
    row.enabled = not bool(disabled)
    await db.commit()
    # 若禁用，主动断开现有连接
    if disabled:
        try:
            from app.services.websocket_service import websocket_manager
            await websocket_manager.disconnect(client_id, "admin_disable")
        except Exception:
            pass
    return {"success": True, "disabled": not row.enabled}


@router.get("/logs/his")
async def list_his_logs(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    message_id: Optional[str] = None,
    pat_no: Optional[str] = None,
    user_code: Optional[str] = None,
):
    """分页查询 HIS 推送日志"""
    conditions = []
    if message_id:
        conditions.append(HisPushLog.message_id == message_id)
    if pat_no:
        conditions.append(HisPushLog.pat_no == pat_no)
    if user_code:
        conditions.append(HisPushLog.user_code == user_code)

    stmt = select(HisPushLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(HisPushLog.created_at.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    rows_res = await db.execute(
        stmt.offset(_page_offset(page, pageSize)).limit(pageSize)
    )
    items: List[HisPushLog] = rows_res.scalars().all()

    def _fmt_dt(dt) -> Optional[str]:
        return dt.isoformat(sep=" ", timespec="seconds") if dt else None

    data = [
        {
            "created_at": _fmt_dt(it.created_at),
            "message_id": it.message_id,
            "pat_no": it.pat_no,
            "user_code": it.user_code,
        }
        for it in items
    ]
    return {"items": data, "total": total}


@router.get("/logs/ai")
async def list_ai_logs(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    request_id: Optional[str] = None,
    pat_no: Optional[str] = None,
    adm_id: Optional[str] = None,
):
    """分页查询 AI 推荐日志"""
    conditions = []
    if request_id:
        conditions.append(AiRecommendationLog.request_id == request_id)
    if pat_no:
        conditions.append(AiRecommendationLog.pat_no == pat_no)
    if adm_id:
        conditions.append(AiRecommendationLog.adm_id == adm_id)

    stmt = select(AiRecommendationLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(AiRecommendationLog.created_at.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    rows_res = await db.execute(
        stmt.offset(_page_offset(page, pageSize)).limit(pageSize)
    )
    items: List[AiRecommendationLog] = rows_res.scalars().all()

    def _fmt_dt(dt) -> Optional[str]:
        return dt.isoformat(sep=" ", timespec="seconds") if dt else None

    data = [
        {
            "created_at": _fmt_dt(it.created_at),
            "request_id": it.request_id,
            "pat_no": it.pat_no,
            "adm_id": it.adm_id,
        }
        for it in items
    ]
    return {"items": data, "total": total}


@router.get("/logs/system")
async def list_system_logs(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    level: Optional[str] = Query(None, description="INFO|WARN|ERROR"),
    module: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """分页查询系统日志"""
    conditions = []
    if level:
        conditions.append(SystemLog.log_level == level)
    if module:
        conditions.append(SystemLog.module == module)
    if request_id:
        conditions.append(SystemLog.request_id == request_id)

    stmt = select(SystemLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(SystemLog.created_at.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    rows_res = await db.execute(
        stmt.offset(_page_offset(page, pageSize)).limit(pageSize)
    )
    items: List[SystemLog] = rows_res.scalars().all()

    def _fmt_dt(dt) -> Optional[str]:
        return dt.isoformat(sep=" ", timespec="seconds") if dt else None

    data = [
        {
            "created_at": _fmt_dt(it.created_at),
            "level": it.log_level,
            "module": it.module,
            "message": it.message,
        }
        for it in items
    ]
    return {"items": data, "total": total}


# ================= 使用统计（简版） =================


@router.get("/usage/summary")
async def usage_summary(
    db: AsyncSession = Depends(get_database),
    client_id: Optional[str] = None,
):
    """简版统计：基于 AiRecommendationLog 做近一天聚合（可按 client_id 过滤）"""
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(days=1)

    stmt = select(AiRecommendationLog).where(AiRecommendationLog.created_at >= since)
    if client_id:
        stmt = stmt.where(AiRecommendationLog.client_id == client_id)

    rows = (await db.execute(stmt)).scalars().all()
    total = len(rows)
    success = len([r for r in rows if r.status == "success"])
    failed = total - success
    if total > 0:
        avg = round(sum(float(r.processing_time or 0) for r in rows) / total, 2)
        p95 = sorted([float(r.processing_time or 0) for r in rows])[max(int(total * 0.95) - 1, 0)]
    else:
        avg = 0.0
        p95 = 0.0
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "avg_seconds": avg,
        "p95_seconds": p95,
    }


@router.get("/usage/service-calls")
async def usage_service_calls(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
):
    """明细：返回最近的 service_calls（简版）"""
    from app.models.database_models import ServiceCall
    stmt = select(ServiceCall).order_by(ServiceCall.started_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))).scalars().all()
    data = [
        {
            "request_id": r.request_id,
            "client_id": r.client_id,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "started_at": (r.started_at.isoformat(sep=" ", timespec="seconds") if r.started_at else None),
        }
        for r in rows
    ]
    return {"items": data, "total": total}


# ================= 会话管理 =================


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    patient_id: Optional[str] = None,
):
    from app.models.database_models import AiSession
    stmt = select(AiSession)
    if patient_id:
        stmt = stmt.where(AiSession.patient_id == patient_id)
    stmt = stmt.order_by(AiSession.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))).scalars().all()
    data = [
        {
            "id": r.id,
            "session_key": r.session_key,
            "patient_id": r.patient_id,
            "visit_id": r.visit_id,
            "doctor_id": r.doctor_id,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds") if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": data, "total": total}


@router.get("/session-records")
async def list_session_records(db: AsyncSession = Depends(get_database), session_id: str = Query(...)):
    from app.models.database_models import AiSessionRecord
    stmt = select(AiSessionRecord).where(AiSessionRecord.session_id == session_id).order_by(AiSessionRecord.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    data = [
        {
            "id": r.id,
            "request_id": r.request_id,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds") if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": data}


# ================= 调用链查询 =================


@router.get("/traces")
async def list_traces(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    trace_id: Optional[str] = None,
    client_id: Optional[str] = None,
):
    stmt = select(TraceRecord)
    if trace_id:
        stmt = stmt.where(TraceRecord.trace_id == trace_id)
    if client_id:
        stmt = stmt.where(TraceRecord.client_id == client_id)
    stmt = stmt.order_by(TraceRecord.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))).scalars().all()
    data = [
        {
            "trace_id": r.trace_id,
            "request_id": r.request_id,
            "client_id": r.client_id,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds") if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": data, "total": total}


@router.get("/spans")
async def list_spans(db: AsyncSession = Depends(get_database), trace_id: str = Query(...)):
    stmt = select(SpanRecord).where(SpanRecord.trace_id == trace_id).order_by(SpanRecord.start_time.asc())
    rows = (await db.execute(stmt)).scalars().all()
    data = [
        {
            "id": r.id,
            "trace_id": r.trace_id,
            "name": r.name,
            "status": r.status,
            "start_time": r.start_time.isoformat(sep=" ", timespec="seconds") if r.start_time else None,
            "end_time": r.end_time.isoformat(sep=" ", timespec="seconds") if r.end_time else None,
            "attributes": r.attributes,
        }
        for r in rows
    ]
    return {"items": data}


# ================= 权限配置 =================


@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
):
    stmt = select(RoleInfo).order_by(RoleInfo.created_at.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))).scalars().all()
    data = [
        {"id": r.id, "name": r.name, "code": r.code, "description": r.description, "status": r.status}
        for r in rows
    ]
    return {"items": data, "total": total}


@router.post("/roles")
async def create_role(payload: RoleCreate, db: AsyncSession = Depends(get_database)):
    exists = (await db.execute(select(RoleInfo).where(RoleInfo.code == payload.code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="角色编码已存在")
    it = RoleInfo(name=payload.name, code=payload.code, description=payload.description, status=payload.status or "enabled")
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return {"id": it.id}


@router.put("/roles/{role_id}")
async def update_role(role_id: str, payload: RoleUpdate, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(RoleInfo).where(RoleInfo.id == role_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="角色不存在")
    if payload.name is not None:
        row.name = payload.name
    if payload.description is not None:
        row.description = payload.description
    if payload.status is not None:
        row.status = payload.status
    await db.commit()
    return {"success": True}


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(RoleInfo).where(RoleInfo.id == role_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="角色不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


@router.get("/role-service-acl")
async def list_role_acl(
    role_id: str,
    db: AsyncSession = Depends(get_database),
):
    rows = (await db.execute(select(RoleServiceAcl).where(RoleServiceAcl.role_id == role_id))).scalars().all()
    data = [
        {"id": r.id, "role_id": r.role_id, "service_id": r.service_id, "endpoint_id": r.endpoint_id, "allow": bool(r.allow)}
        for r in rows
    ]
    return {"items": data}


@router.post("/role-service-acl")
async def create_role_acl(payload: RoleAclCreate, db: AsyncSession = Depends(get_database)):
    it = RoleServiceAcl(role_id=payload.role_id, service_id=payload.service_id, endpoint_id=payload.endpoint_id, allow=payload.allow)
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return {"id": it.id}


@router.delete("/role-service-acl/{acl_id}")
async def delete_role_acl(acl_id: str, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(RoleServiceAcl).where(RoleServiceAcl.id == acl_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


@router.get("/client-role-binding")
async def list_client_role_binding(client_id: str, db: AsyncSession = Depends(get_database)):
    rows = (await db.execute(select(ClientRoleBinding).where(ClientRoleBinding.client_id == client_id))).scalars().all()
    data = [{"id": r.id, "client_id": r.client_id, "role_id": r.role_id} for r in rows]
    return {"items": data}


@router.post("/client-role-binding")
async def create_client_role_binding(payload: ClientRoleBindCreate, db: AsyncSession = Depends(get_database)):
    it = ClientRoleBinding(client_id=payload.client_id, role_id=payload.role_id)
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return {"id": it.id}


@router.delete("/client-role-binding/{bind_id}")
async def delete_client_role_binding(bind_id: str, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(ClientRoleBinding).where(ClientRoleBinding.id == bind_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="绑定不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


# ================= 服务治理 =================


@router.get("/services")
async def list_services(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    keyword: Optional[str] = None,
    kind: Optional[str] = Query(None, description="hospital|model"),
):
    stmt = select(Service)
    if keyword:
        stmt = stmt.where((Service.name.like(f"%{keyword}%")) | (Service.base_path.like(f"%{keyword}%")))
    # kind 兼容参数不再使用；服务类型改为 HIS_SERVICE / MODEL_SERVICE
    stmt = stmt.order_by(Service.create_time.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()
    rows_res = await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))
    items: List[Service] = rows_res.scalars().all()

    data = [
        {
            "id": it.id,
            "name": it.name,
            "type": it.type,
            "base_path": it.base_path,
            "protocol": it.protocol,
            "enabled": bool(it.enabled),
            "description": it.description,
            "create_time": it.create_time.isoformat(sep=" ", timespec="seconds") if it.create_time else None,
            "update_time": it.update_time.isoformat(sep=" ", timespec="seconds") if it.update_time else None,
        }
        for it in items
    ]
    return {"items": data, "total": total}


@router.post("/services")
async def create_service(payload: ServiceCreate, db: AsyncSession = Depends(get_database)):
    it = Service(
        name=payload.name,
        type=payload.type,
        base_path=payload.base_path,
        protocol=payload.protocol,
        enabled=bool(payload.enabled),
        description=payload.description,
    )
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return {"id": it.id}


@router.put("/services/{service_id}")
async def update_service(service_id: str, payload: ServiceUpdate, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="服务不存在")
    if payload.name is not None:
        row.name = payload.name
    if payload.type is not None:
        row.type = payload.type
    if payload.base_path is not None:
        row.base_path = payload.base_path
    if payload.protocol is not None:
        row.protocol = payload.protocol
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.description is not None:
        row.description = payload.description
    await db.commit()
    return {"success": True}


@router.delete("/services/{service_id}")
async def delete_service(service_id: str, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="服务不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


@router.get("/service-endpoints")
async def list_service_endpoints(
    db: AsyncSession = Depends(get_database),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=200),
    service_id: Optional[str] = None,
):
    stmt = select(ServiceInterface)
    if service_id:
        stmt = stmt.where(ServiceInterface.service_id == service_id)
    stmt = stmt.order_by(ServiceInterface.create_time.desc())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()
    rows_res = await db.execute(stmt.offset(_page_offset(page, pageSize)).limit(pageSize))
    items: List[ServiceInterface] = rows_res.scalars().all()

    data = [
        {
            "id": it.id,
            "service_id": it.service_id,
            "name": it.name,
            "url": it.target_url or "",
            "method": it.method,
            "timeout_ms": (it.timeout_seconds or 5) * 1000,
            "status": ("enabled" if it.enabled else "disabled"),
        }
        for it in items
    ]
    return {"items": data, "total": total}


@router.post("/service-endpoints")
async def create_service_endpoint(payload: ServiceEndpointCreate, db: AsyncSession = Depends(get_database)):
    # 基础存在性检查
    svc = (await db.execute(select(Service).where(Service.id == payload.service_id))).scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=400, detail="所属服务不存在")
    it = ServiceInterface(
        service_id=payload.service_id,
        name=payload.name,
        path=getattr(payload, "path", None) or payload.url,
        method=payload.method or "POST",
        target_url=getattr(payload, "target_url", None) or payload.url,
        timeout_seconds=max(1, int(((getattr(payload, "timeout_seconds", None) or 5) if getattr(payload, "timeout_seconds", None) else (payload.timeout_ms or 10000)) / 1000)),
        enabled=True if (getattr(payload, "enabled", None) if getattr(payload, "enabled", None) is not None else (payload.status or "enabled")) == "enabled" else False,
    )
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return {"id": it.id}


@router.put("/service-endpoints/{endpoint_id}")
async def update_service_endpoint(endpoint_id: str, payload: ServiceEndpointUpdate, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(ServiceInterface).where(ServiceInterface.id == endpoint_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="端点不存在")
    if payload.name is not None:
        row.name = payload.name
    if getattr(payload, "path", None) is not None:
        row.path = payload.path  # type: ignore
    if getattr(payload, "target_url", None) is not None:
        row.target_url = payload.target_url  # type: ignore
    if getattr(payload, "url", None) is not None:
        row.target_url = payload.url  # 向后兼容
    if payload.method is not None:
        row.method = payload.method
    if getattr(payload, "timeout_seconds", None) is not None:
        row.timeout_seconds = int(payload.timeout_seconds)  # type: ignore
    if getattr(payload, "timeout_ms", None) is not None:
        row.timeout_seconds = max(1, int(payload.timeout_ms / 1000))  # 向后兼容
    if getattr(payload, "enabled", None) is not None:
        row.enabled = bool(payload.enabled)  # type: ignore
    if getattr(payload, "status", None) is not None:
        row.enabled = True if payload.status == "enabled" else False  # 向后兼容
    await db.commit()
    return {"success": True}


@router.delete("/service-endpoints/{endpoint_id}")
async def delete_service_endpoint(endpoint_id: str, db: AsyncSession = Depends(get_database)):
    row = (await db.execute(select(ServiceInterface).where(ServiceInterface.id == endpoint_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="端点不存在")
    await db.delete(row)
    await db.commit()
    return {"success": True}


@router.post("/service-endpoints/{endpoint_id}/test-connection")
async def test_service_endpoint_connection(endpoint_id: str, db: AsyncSession = Depends(get_database)) -> TestConnectionResult:
    row = (await db.execute(select(ServiceInterface).where(ServiceInterface.id == endpoint_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="端点不存在")

    try:
        timeout = float(row.timeout_seconds or 5)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(row.method or "POST", row.target_url or "")
            return TestConnectionResult(ok=resp.status_code < 500, status_code=resp.status_code)
    except Exception as e:
        return TestConnectionResult(ok=False, error=str(e))


