"""
WebSocket路由管理
处理WebSocket连接和消息
ws://localhost:8000/ws/client/{client_id}
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import json
from loguru import logger

from app.core.database import get_database
from app.services.websocket_service import websocket_manager, WebSocketService
from app.schemas.websocket_schemas import MessageType
from app.services.ai_service import AiService
from app.services.his_service import HisService
from sqlalchemy import select, and_
from app.models.database_models import HisPushLog
from app.schemas.his_schemas import CDSSMessage, ItemData

router = APIRouter()


@router.websocket("/client/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    client_id: str,
    db: AsyncSession = Depends(get_database)
):
    """
    WebSocket连接端点
    客户端连接路径: ws://localhost:8000/ws/client/{client_id}
    client_id格式: client_{deptCode}_{userCode}
    """
    
    try:
        logger.bind(name="app.api.routes.websocket_manager").info(
            f"🔄 WebSocket连接请求: client_id={client_id}"
        )
        
        # 建立连接
        await websocket_manager.connect(websocket, client_id, db)
        
        while True:
            try:
                # 接收客户端消息
                data = await websocket.receive_text()
                message = json.loads(data)
                
                logger.bind(name="app.api.routes.websocket_manager").info(
                    f"📥 收到客户端消息: client_id={client_id}, type={message.get('type')}"
                )
                
                # 处理不同类型的消息
                await handle_client_message(client_id, message, db)
                
            except WebSocketDisconnect:
                logger.bind(name="app.api.routes.websocket_manager").info(
                    f"🔌 客户端主动断开: client_id={client_id}"
                )
                break
            except json.JSONDecodeError:
                logger.bind(name="app.api.routes.websocket_manager").error(
                    f"❌ 消息格式错误: client_id={client_id}"
                )
                await websocket_manager.send_error(
                    client_id, 
                    "MSG_001", 
                    "消息格式错误", 
                    "JSON解析失败"
                )
            except Exception as e:
                logger.bind(name="app.api.routes.websocket_manager").error(
                    f"❌ 处理消息异常: client_id={client_id}, error={e}"
                )
                await websocket_manager.send_error(
                    client_id, 
                    "MSG_003", 
                    "消息处理异常", 
                    str(e)
                )
    
    except Exception as e:
        logger.bind(name="app.api.routes.websocket_manager").error(
            f"❌ WebSocket连接异常: client_id={client_id}, error={e}"
        )
    
    finally:
        # 断开连接清理
        await websocket_manager.disconnect(client_id, "connection_closed")
        
        # 更新数据库连接状态
        try:
            await websocket_manager._update_client_connection(db, client_id, "disconnected", "", "")
        except:
            pass


async def handle_client_message(client_id: str, message: dict, db: AsyncSession):
    """处理客户端消息"""
    
    message_type = message.get('type')
    message_data = message.get('data', {})
    
    try:
        if message_type == MessageType.HEARTBEAT.value:
            # 处理心跳消息
            await handle_heartbeat(client_id, message_data)
        
        elif message_type == "ai_recommend_request":
            # 通过WS发起AI推荐请求
            await handle_ai_recommend_request(client_id, message_data, db)

        elif message_type == "ack":
            # 处理确认消息（暂时简单记录）
            logger.bind(name="app.api.routes.websocket_manager").info(
                f"📝 收到确认消息: client_id={client_id}, original_id={message_data.get('originalMessageId')}"
            )
        
        else:
            logger.bind(name="app.api.routes.websocket_manager").warning(
                f"⚠️ 未知消息类型: client_id={client_id}, type={message_type}"
            )
            await websocket_manager.send_error(
                client_id,
                "MSG_002",
                "消息类型不支持",
                f"不支持的消息类型: {message_type}"
            )
    
    except Exception as e:
        logger.bind(name="app.api.routes.websocket_manager").error(
            f"❌ 处理客户端消息异常: {e}"
        )
        await websocket_manager.send_error(
            client_id,
            "MSG_003",
            "消息处理异常",
            str(e)
        )


async def handle_heartbeat(client_id: str, data: dict):
    """处理心跳消息"""
    try:
        # 更新心跳时间
        await websocket_manager.update_heartbeat(client_id)
        
        # 回复心跳
        await websocket_manager.send_heartbeat(client_id)
        
        logger.bind(name="app.api.routes.websocket_manager").debug(
            f"💓 心跳处理: client_id={client_id}"
        )
        
    except Exception as e:
        logger.bind(name="app.api.routes.websocket_manager").error(
            f"❌ 心跳处理异常: {e}"
        )


async def handle_ai_recommend_request(client_id: str, data: dict, db: AsyncSession):
    """处理AI推荐请求（WS端到端流式）"""
    try:
        request_id = data.get("requestId")
        patient_id = data.get("patientId")
        visit_id = data.get("visitId")
        doctor_id = data.get("doctorId")
        if not (request_id and patient_id and visit_id and doctor_id):
            await websocket_manager.send_error(client_id, "REQ_001", "请求参数不完整", "缺少requestId/patientId/visitId/doctorId")
            return

        # 查找最近的HIS推送记录（以时间倒序取最新，避免时区造成的created_at筛选失效）
        # 记录请求参数
        logger.bind(name="app.api.routes.websocket_manager").info(
            f"[AI-REQ] 查找HIS日志: pat_no={patient_id}, adm_id={visit_id}, doctor_id={doctor_id}"
        )

        # 优先策略：按照 患者ID + 医生ID 精确匹配，取最新一条
        q1 = (
            select(HisPushLog)
            .where(
                and_(
                    HisPushLog.pat_no == patient_id,
                    HisPushLog.user_code == doctor_id,
                )
            )
            .order_by(HisPushLog.created_at.desc())
            .limit(1)
        )
        res1 = await db.execute(q1)
        his_log = res1.scalars().first()

        # 兜底：按照 患者ID + 就诊ID 匹配，取最新一条（HIS若按就诊维度推送则可命中）
        if not his_log and visit_id:
            q2 = (
                select(HisPushLog)
                .where(
                    and_(HisPushLog.pat_no == patient_id, HisPushLog.adm_id == visit_id)
                )
                .order_by(HisPushLog.created_at.desc())
                .limit(1)
            )
            res2 = await db.execute(q2)
            his_log = res2.scalars().first()

        # 最后兜底：仅按 医生ID 近5分钟 取最新一条
        if not his_log:
            from datetime import datetime, timedelta
            logger.bind(name="app.api.routes.websocket_manager").warning(
                f"[AI-REQ] 放宽到doctor_id近5分钟: doctor_id={doctor_id}"
            )
            q3 = (
                select(HisPushLog)
                .where(
                    and_(
                        HisPushLog.user_code == doctor_id,
                        HisPushLog.created_at >= datetime.now() - timedelta(minutes=5),
                    )
                )
                .order_by(HisPushLog.created_at.desc())
                .limit(1)
            )
            res3 = await db.execute(q3)
            his_log = res3.scalars().first()

        if not his_log:
            await websocket_manager.send_error(
                client_id,
                "REQ_404",
                "未找到患者病历数据",
                "请确保HIS系统已推送患者信息",
            )
            return

        logger.bind(name="app.api.routes.websocket_manager").info(
            f"[AI-REQ] 命中HIS日志: id={his_log.id}, pat_no={his_log.pat_no}, adm_id={his_log.adm_id}, created_at={his_log.created_at}"
        )

        # 重建CDSS消息
        import json as _json
        item_dict = _json.loads(his_log.item_data) if his_log.item_data else {}
        item = ItemData(**item_dict)
        cdss_message = CDSSMessage(
            systemId=his_log.system_id,
            sceneType=his_log.scene_type,
            state=his_log.state,
            patNo=his_log.pat_no,
            patName=his_log.pat_name or "",
            admId=his_log.adm_id,
            visitType=his_log.visit_type or "",
            deptCode=his_log.dept_code or None,
            deptDesc=his_log.dept_desc or None,
            hospCode=his_log.hosp_code or None,
            hospDesc=his_log.hosp_desc or None,
            userIP=his_log.user_ip or "",
            userCode=his_log.user_code,
            userName=his_log.user_name or "",
            msgTime=his_log.msg_time.strftime("%Y-%m-%d %H:%M:%S") if his_log.msg_time else "",
            remark=his_log.remark or "",
            itemData=item,
        )

        ai_service = AiService(db)
        ws_service = WebSocketService()

        # 流式调用并推送
        await ai_service.call_ai_recommendation_streaming(
            cdss_message=cdss_message,
            request_id=request_id,
            client_id=client_id,
            websocket_service=ws_service,
            his_push_log_id=his_log.id,
        )

    except Exception as e:
        logger.bind(name="app.api.routes.websocket_manager").error(
            f"❌ 处理AI推荐请求异常: {e}"
        )
        await websocket_manager.send_error(client_id, "SRV_500", "服务器内部错误", str(e))


@router.get("/clients")
async def get_connected_clients():
    """获取所有连接的客户端信息（调试用）"""
    try:
        clients = await websocket_manager.get_connected_clients()
        return {
            "code": 200,
            "message": "获取成功",
            "data": {
                "total": len(clients),
                "clients": clients
            }
        }
    except Exception as e:
        logger.error(f"❌ 获取客户端信息异常: {e}")
        return {
            "code": 500,
            "message": "获取失败",
            "error": str(e)
        }