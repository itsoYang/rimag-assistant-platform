"""
WebSocket消息相关的Pydantic模型
符合WebSocket连接规范的数据结构定义
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    """消息类型枚举"""
    HEARTBEAT = "heartbeat"
    PATIENT_DATA = "patient_data"
    AI_RECOMMENDATION = "ai_recommendation"
    ERROR = "error"


class ConnectionStatus(str, Enum):
    """连接状态枚举"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


class BaseMessage(BaseModel):
    """基础消息格式"""
    type: MessageType = Field(..., description="消息类型")
    id: str = Field(..., description="消息唯一ID")
    timestamp: str = Field(..., description="时间戳（ISO 8601格式）")
    data: Dict[str, Any] = Field(..., description="消息数据")


class HeartbeatData(BaseModel):
    """心跳消息数据"""
    status: str = Field(default="alive", description="状态")


class PatientData(BaseModel):
    """患者信息数据"""
    patNo: str = Field(..., description="患者登记号")
    patName: str = Field(..., description="患者姓名")
    admId: str = Field(..., description="就诊流水号")
    deptCode: str = Field(..., description="科室代码")
    deptDesc: str = Field(..., description="科室名称")
    userCode: str = Field(..., description="用户代码")
    userName: str = Field(..., description="用户名称")
    patientInfo: Dict[str, str] = Field(..., description="患者详细信息")


class RecommendationItem(BaseModel):
    """推荐项目"""
    checkItemName: str = Field(..., description="检查项目名称")
    reason: str = Field(..., description="推荐理由")
    cautions: str = Field(..., description="注意事项")
    sequence: int = Field(..., description="序号")


class AiRecommendationData(BaseModel):
    """AI推荐数据"""
    requestId: str = Field(..., description="请求ID")
    patNo: str = Field(..., description="患者登记号")
    recommendations: List[RecommendationItem] = Field(..., description="推荐列表")
    totalCount: int = Field(..., description="总数量")
    processingTime: float = Field(..., description="处理时间（秒）")
    aiService: str = Field(..., description="AI服务名称")
    # 流式标记（可选）
    partial: bool | None = Field(default=None, description="是否为部分增量数据")
    finish: bool | None = Field(default=None, description="是否为最终完成消息")


class ErrorData(BaseModel):
    """错误消息数据"""
    errorCode: str = Field(..., description="错误码")
    errorMessage: str = Field(..., description="错误消息")
    details: Optional[str] = Field(None, description="错误详情")


class HeartbeatMessage(BaseMessage):
    """心跳消息"""
    type: MessageType = Field(default=MessageType.HEARTBEAT)
    data: HeartbeatData


class PatientDataMessage(BaseMessage):
    """患者信息推送消息"""
    type: MessageType = Field(default=MessageType.PATIENT_DATA)
    data: PatientData


class AiRecommendationMessage(BaseMessage):
    """AI推荐结果消息"""
    type: MessageType = Field(default=MessageType.AI_RECOMMENDATION)
    data: AiRecommendationData


class ErrorMessage(BaseMessage):
    """错误消息"""
    type: MessageType = Field(default=MessageType.ERROR)
    data: ErrorData


class ClientConnectionInfo(BaseModel):
    """客户端连接信息"""
    client_id: str = Field(..., description="客户端ID")
    doctor_id: str = Field(..., description="医生ID")
    doctor_name: Optional[str] = Field(None, description="医生姓名")
    ip_address: str = Field(..., description="IP地址")
    connection_status: ConnectionStatus = Field(..., description="连接状态")
    connected_at: datetime = Field(..., description="连接时间")
    last_heartbeat: Optional[datetime] = Field(None, description="最后心跳时间")