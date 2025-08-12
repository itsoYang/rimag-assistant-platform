"""
WebSocket连接管理服务
处理客户端连接、消息推送、心跳检测
"""

from typing import Dict, Set, Optional
import json
import uuid
from datetime import datetime
from fastapi import WebSocket
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.database_models import ClientConnection, SystemLog
from app.schemas.his_schemas import CDSSMessage
from app.schemas.websocket_schemas import (
    MessageType, PatientDataMessage, PatientData, 
    HeartbeatMessage, HeartbeatData, ErrorMessage, ErrorData
)


class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 活跃连接字典 {client_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # 客户端信息字典 {client_id: client_info}
        self.client_info: Dict[str, dict] = {}
        # 心跳监控
        self.heartbeat_tasks: Dict[str, bool] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str, db: AsyncSession):
        """客户端连接"""
        try:
            await websocket.accept()
            
            # 如果已存在连接，先断开旧连接
            if client_id in self.active_connections:
                await self.disconnect(client_id, "new_connection_replace")
            
            # 添加新连接
            self.active_connections[client_id] = websocket
            
            # 获取客户端IP
            client_ip = websocket.client.host if websocket.client else "unknown"
            
            # 解析client_id获取医生信息 (格式: client_{deptCode}_{userCode})
            parts = client_id.split('_')
            doctor_id = parts[-1] if len(parts) >= 3 else "unknown"
            
            # 保存客户端信息
            self.client_info[client_id] = {
                "doctor_id": doctor_id,
                "ip_address": client_ip,
                "connected_at": datetime.now(),
                "last_heartbeat": datetime.now()
            }
            
            # 更新数据库连接记录
            await self._update_client_connection(db, client_id, "connected", client_ip, doctor_id)
            
            logger.bind(name="app.services.websocket_service").info(
                f"🔗 WebSocket连接建立: client_id={client_id}, ip={client_ip}"
            )
            
            # 发送连接确认消息
            await self.send_heartbeat(client_id)
            
        except Exception as e:
            logger.error(f"❌ WebSocket连接失败: client_id={client_id}, error={e}")
            raise
    
    async def disconnect(self, client_id: str, reason: str = "client_disconnect"):
        """断开客户端连接"""
        try:
            if client_id in self.active_connections:
                websocket = self.active_connections[client_id]
                try:
                    await websocket.close()
                except:
                    pass
                
                # 移除连接
                del self.active_connections[client_id]
                
                if client_id in self.client_info:
                    del self.client_info[client_id]
                
                if client_id in self.heartbeat_tasks:
                    del self.heartbeat_tasks[client_id]
                
                logger.bind(name="app.services.websocket_service").info(
                    f"🔌 WebSocket连接断开: client_id={client_id}, reason={reason}"
                )
        
        except Exception as e:
            logger.bind(name="app.services.websocket_service").error(
                f"❌ 断开WebSocket连接异常: {e}"
            )
    
    async def send_message(self, client_id: str, message_type: MessageType, data: dict) -> bool:
        """发送消息给指定客户端"""
        try:
            if client_id not in self.active_connections:
                logger.bind(name="app.services.websocket_service").warning(
                    f"⚠️ 客户端未连接: client_id={client_id}"
                )
                return False
            
            websocket = self.active_connections[client_id]
            
            # 构造消息
            message = {
                "type": message_type.value,
                "id": f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}",
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            
            # 发送消息
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
            
            logger.bind(name="app.services.websocket_service").info(
                f"📤 消息发送成功: client_id={client_id}, type={message_type.value}"
            )
            return True
            
        except Exception as e:
            logger.bind(name="app.services.websocket_service").error(
                f"❌ 发送消息失败: client_id={client_id}, error={e}"
            )
            # 连接可能已断开，移除连接
            await self.disconnect(client_id, "send_message_failed")
            return False
    
    async def send_heartbeat(self, client_id: str) -> bool:
        """发送心跳消息"""
        return await self.send_message(
            client_id,
            MessageType.HEARTBEAT,
            {"status": "alive"}
        )
    
    async def send_error(self, client_id: str, error_code: str, error_message: str, details: str = None) -> bool:
        """发送错误消息"""
        return await self.send_message(
            client_id,
            MessageType.ERROR,
            {
                "errorCode": error_code,
                "errorMessage": error_message,
                "details": details,
            }
        )
    
    async def broadcast(self, message_type: MessageType, data: dict, exclude_clients: Set[str] = None):
        """广播消息给所有连接的客户端"""
        exclude_clients = exclude_clients or set()
        
        for client_id in list(self.active_connections.keys()):
            if client_id not in exclude_clients:
                await self.send_message(client_id, message_type, data)
    
    async def get_connected_clients(self) -> Dict[str, dict]:
        """获取所有连接的客户端信息"""
        return self.client_info.copy()
    
    async def update_heartbeat(self, client_id: str):
        """更新客户端心跳时间"""
        if client_id in self.client_info:
            self.client_info[client_id]["last_heartbeat"] = datetime.now()
    
    async def _update_client_connection(self, db: AsyncSession, client_id: str, status: str, ip_address: str, doctor_id: str):
        """更新数据库中的客户端连接记录"""
        try:
            # 查找现有记录
            query = select(ClientConnection).where(ClientConnection.client_id == client_id)
            result = await db.execute(query)
            existing = result.scalar_one_or_none()
            
            if existing:
                # 更新现有记录
                existing.connection_status = status
                existing.last_heartbeat = datetime.now()
                if status == "connected":
                    existing.connected_at = datetime.now()
                    existing.disconnected_at = None
                elif status == "disconnected":
                    existing.disconnected_at = datetime.now()
            else:
                # 创建新记录
                new_connection = ClientConnection(
                    client_id=client_id,
                    doctor_id=doctor_id,
                    connection_status=status,
                    ip_address=ip_address,
                    connected_at=datetime.now() if status == "connected" else None,
                    last_heartbeat=datetime.now()
                )
                db.add(new_connection)
            
            await db.commit()
            
        except Exception as e:
            await db.rollback()
            logger.bind(name="app.services.websocket_service").error(
                f"❌ 更新客户端连接记录失败: {e}"
            )


# 全局WebSocket管理器实例
websocket_manager = WebSocketManager()


class WebSocketService:
    """WebSocket业务服务"""
    
    def __init__(self):
        self.manager = websocket_manager
    
    async def push_patient_data(self, client_id: str, cdss_message: CDSSMessage, message_id: str) -> bool:
        """推送患者数据到客户端"""
        try:
            # 构造患者数据
            patient_data = {
                "patNo": cdss_message.patNo,
                "patName": cdss_message.patName,
                "admId": cdss_message.admId,
                "deptCode": cdss_message.deptCode or "",
                "deptDesc": cdss_message.deptDesc or "",
                "userCode": cdss_message.userCode,
                "userName": cdss_message.userName or "",
                "patientInfo": {
                    "patientAge": cdss_message.itemData.patientAge,
                    "patientSex": cdss_message.itemData.patientSex,
                    "clinicInfo": cdss_message.itemData.clinicInfo,
                    "abstractHistory": cdss_message.itemData.abstractHistory
                }
            }
            
            # 发送患者数据消息
            success = await self.manager.send_message(
                client_id,
                MessageType.PATIENT_DATA,
                patient_data
            )
            
            if success:
                logger.bind(name="app.services.websocket_service").info(
                    f"✅ 患者数据推送成功: client_id={client_id}, message_id={message_id}"
                )
            else:
                logger.bind(name="app.services.websocket_service").error(
                    f"❌ 患者数据推送失败: client_id={client_id}, message_id={message_id}"
                )
            
            return success
            
        except Exception as e:
            logger.bind(name="app.services.websocket_service").error(
                f"❌ 推送患者数据异常: {e}"
            )
            return False
    
    async def push_ai_recommendation(
        self,
        client_id: str,
        request_id: str,
        recommendations: list,
        processing_time: float,
        pat_no: str = "",
        partial: bool | None = None,
        finish: bool | None = None,
    ) -> bool:
        """推送AI推荐结果到客户端（支持流式标记）"""
        try:
            # 构造AI推荐数据
            ai_data = {
                "requestId": request_id,
                "recommendations": recommendations,
                "totalCount": len(recommendations),
                "processingTime": processing_time,
                "aiService": "rimagai_checkitem",
                "patNo": pat_no,
            }
            if partial is not None:
                ai_data["partial"] = partial
            if finish is not None:
                ai_data["finish"] = finish
            
            # 发送AI推荐消息
            success = await self.manager.send_message(
                client_id,
                MessageType.AI_RECOMMENDATION,
                ai_data
            )
            
            if success:
                logger.bind(name="app.services.websocket_service").info(
                    f"✅ AI推荐推送成功: client_id={client_id}, request_id={request_id}"
                )
            else:
                logger.bind(name="app.services.websocket_service").error(
                    f"❌ AI推荐推送失败: client_id={client_id}, request_id={request_id}"
                )
            
            return success
            
        except Exception as e:
            logger.bind(name="app.services.websocket_service").error(
                f"❌ 推送AI推荐异常: {e}"
            )
            return False