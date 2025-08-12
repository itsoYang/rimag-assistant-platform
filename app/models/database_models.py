"""
数据库模型定义
按照MVP阶段实施方案定义的表结构
"""

from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.sql.sqltypes import Numeric
from sqlalchemy.sql import func
from app.core.database import Base

# UUID v7 生成（字符串 36 位）
try:
    # uuid6 库提供 uuid7 实现，Python 3.11 环境可用
    from uuid6 import uuid7

    def uuid7_str() -> str:  # noqa: D401
        return str(uuid7())
except Exception:  # 回退：严格环境需要安装 uuid6；开发期可临时退化为 v4
    from uuid import uuid4

    def uuid7_str() -> str:  # type: ignore
        return str(uuid4())


class ClientConnection(Base):
    """客户端连接表"""
    __tablename__ = "client_connections"
    
    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    client_id = Column(String(50), unique=True, nullable=False, comment="客户端唯一标识")
    doctor_id = Column(String(50), nullable=False, comment="医生ID")
    doctor_name = Column(String(100), comment="医生姓名")
    connection_status = Column(String(20), default='connected', comment="连接状态")
    websocket_id = Column(String(100), comment="WebSocket连接ID")
    ip_address = Column(String(45), comment="IP地址")
    connected_at = Column(DateTime, default=func.current_timestamp(), comment="连接时间")
    last_heartbeat = Column(DateTime, default=func.current_timestamp(), comment="最后心跳时间")
    disconnected_at = Column(DateTime, comment="断开时间")


class HisPushLog(Base):
    """HIS推送记录表（CDSS消息框架）"""
    __tablename__ = "his_push_logs"
    
    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    message_id = Column(String(50), unique=True, nullable=False, comment="消息唯一ID")
    system_id = Column(String(50), nullable=False, comment="系统ID")
    scene_type = Column(String(20), default='EXAM001', comment="场景类型（检查项目推荐）")
    state = Column(Integer, default=0, comment="状态（0:新增,1:更新,-1:撤销）")
    pat_no = Column(String(50), nullable=False, comment="患者登记号")
    pat_name = Column(String(100), comment="患者姓名")
    adm_id = Column(String(50), nullable=False, comment="就诊流水号")
    visit_type = Column(String(10), comment="就诊类型")
    dept_code = Column(String(20), comment="科室代码")
    dept_desc = Column(String(100), comment="科室名称")
    hosp_code = Column(String(50), comment="院区代码")
    hosp_desc = Column(String(100), comment="院区名称")
    user_ip = Column(String(45), comment="客户端IP")
    user_code = Column(String(50), comment="用户代码（医生ID）")
    user_name = Column(String(100), comment="用户名称")
    msg_time = Column(DateTime, comment="HIS消息时间")
    remark = Column(Text, comment="备注")
    item_data = Column(Text, comment="场景数据（JSON格式）")
    client_id = Column(String(50), comment="关联的客户端ID")
    push_status = Column(String(20), default='success', comment="推送状态")
    error_message = Column(Text, comment="错误信息")
    created_at = Column(DateTime, default=func.current_timestamp(), comment="记录创建时间")


class AiRecommendationLog(Base):
    """AI推荐记录表"""
    __tablename__ = "ai_recommendation_logs"
    
    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    request_id = Column(String(50), unique=True, nullable=False, comment="请求ID")
    client_id = Column(String(50), nullable=False, comment="客户端ID")
    pat_no = Column(String(50), nullable=False, comment="患者登记号（来自CDSS）")
    adm_id = Column(String(50), nullable=False, comment="就诊流水号（来自CDSS）")
    user_code = Column(String(50), nullable=False, comment="用户代码（医生ID，来自CDSS）")
    dept_code = Column(String(20), comment="科室代码（来自CDSS）")
    message_id = Column(String(50), comment="关联CDSS消息ID")
    # 业务层面关联：不使用强外键
    his_push_log_id = Column(String(36), comment="关联HIS推送记录ID")
    ai_request_data = Column(Text, nullable=False, comment="JSON格式的AI服务请求数据")
    ai_response_data = Column(Text, comment="JSON格式的AI服务完整响应")
    recommendations = Column(Text, comment="JSON格式的最终推荐结果")
    processing_time = Column(Numeric(5, 2), comment="处理时间（秒）")
    ai_service_url = Column(String(200), comment="AI服务地址")
    session_id = Column(String(50), comment="AI服务会话ID")
    status = Column(String(20), default='success', comment="处理状态")
    error_message = Column(Text, comment="错误信息")
    created_at = Column(DateTime, default=func.current_timestamp(), comment="创建时间")


class SystemLog(Base):
    """系统日志表"""
    __tablename__ = "system_logs"
    
    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    log_level = Column(String(10), nullable=False, comment="日志级别")
    module = Column(String(50), nullable=False, comment="模块名称")
    operation = Column(String(100), nullable=False, comment="操作描述")
    client_id = Column(String(50), comment="客户端ID")
    request_id = Column(String(50), comment="请求ID")
    push_id = Column(String(50), comment="推送ID")
    message = Column(Text, nullable=False, comment="日志消息")
    details = Column(Text, comment="JSON格式的详细信息")
    created_at = Column(DateTime, default=func.current_timestamp(), comment="创建时间")