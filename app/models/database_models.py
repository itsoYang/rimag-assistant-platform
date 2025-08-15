"""
数据库模型定义
按照MVP阶段实施方案定义的表结构
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Date
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


"""
移除旧版 client_connections/Service/ServiceEndpoint/角色等模型，全面对齐 docs/12-数据库表设计.md
"""


class ClientInfo(Base):
    """客户端信息表（与 docs/12-数据库表设计.md 对齐）

    说明：不使用数据库外键约束，引用完整性由应用层保证。
    """
    __tablename__ = "client_info"

    client_id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    hospital_id = Column(String(64), nullable=True)
    department = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)
    client_version = Column(String(20), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    connected = Column(Boolean, nullable=False, default=False)
    connected_at = Column(DateTime, nullable=True)
    last_active = Column(DateTime, nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class SysDict(Base):
    """系统字典表（docs/12-数据库表设计.md）"""
    __tablename__ = "sys_dict"

    id = Column(String(36), primary_key=True, nullable=False)
    dict_type = Column(String(50), nullable=False)
    dict_key = Column(String(50), nullable=False)
    dict_value = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)

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


# ========== 以下为管理端增强阶段新增的数据模型 ==========


class Service(Base):
    """服务定义表（对齐 docs）"""
    __tablename__ = "services"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)
    base_path = Column(String(200), nullable=False)
    protocol = Column(String(10), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class ServiceInterface(Base):
    """接口注册表（对齐 docs）"""
    __tablename__ = "service_interface"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    service_id = Column(String(36), nullable=False)
    name = Column(String(100), nullable=False)
    path = Column(String(200), nullable=False)
    method = Column(String(10), nullable=False)
    target_url = Column(String(500), nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=5)
    enabled = Column(Boolean, nullable=False, default=True)
    request_sample = Column(Text, nullable=True)
    response_schema = Column(Text, nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class RoleInfo(Base):
    """权限组表（对齐 docs）"""
    __tablename__ = "role_info"

    role_id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    role_name = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(20), nullable=True, default='DEPT')
    enabled = Column(Boolean, nullable=False, default=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class RoleServiceAcl(Base):
    """权限组-服务授权（对齐 docs，授权到服务）"""
    __tablename__ = "role_service_acl"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    role_id = Column(String(36), nullable=False)
    service_id = Column(String(36), nullable=False)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class ClientRoleBinding(Base):
    """客户端-权限组绑定（对齐 docs）"""
    __tablename__ = "client_role_binding"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    client_id = Column(String(36), nullable=False)
    role_id = Column(String(36), nullable=False)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class ServiceCall(Base):
    """服务调用明细（对齐 docs）"""
    __tablename__ = "service_calls"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    client_id = Column(String(36), nullable=False)
    service_id = Column(String(36), nullable=False)
    started_at = Column(DateTime, nullable=False, default=func.current_timestamp())
    ended_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Integer, nullable=True)
    req_summary = Column(Text, nullable=True)
    resp_summary = Column(Text, nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class AiSession(Base):
    """会话主表（对齐 docs）"""
    __tablename__ = "ai_session"

    id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    session_key = Column(String(80), nullable=False)
    patient_id = Column(String(64), nullable=False)
    client_id = Column(String(36), nullable=False)
    hospital_id = Column(String(64), nullable=True)
    session_date = Column(Date, nullable=False)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    update_time = Column(DateTime, default=func.current_timestamp(), nullable=False)
    status = Column(String(20), nullable=False, default='ACTIVE')


class AiSessionRecord(Base):
    """会话记录表（对齐 docs）"""
    __tablename__ = "ai_session_record"

    record_id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    session_id = Column(String(36), nullable=False)
    trace_id = Column(String(36), nullable=True)
    service_name = Column(String(50), nullable=False)
    request_time = Column(DateTime, nullable=False, default=func.current_timestamp())
    request_data = Column(Text, nullable=True)
    response_data = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    # SQLAlchemy Declarative 保留名 'metadata'，需更换属性名，同时列名仍为 'metadata'
    meta_data = Column("metadata", Text, nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class TraceRecord(Base):
    """调用链主表（对齐 docs）"""
    __tablename__ = "trace_record"

    trace_id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    patient_id = Column(String(64), nullable=True)
    hospital_id = Column(String(64), nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)
    total_duration_ms = Column(Integer, nullable=False)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)


class SpanRecord(Base):
    """调用片段表（对齐 docs）"""
    __tablename__ = "span_record"

    span_id = Column(String(36), primary_key=True, default=uuid7_str, nullable=False)
    trace_id = Column(String(36), nullable=False)
    parent_span_id = Column(String(36), nullable=True)
    service_name = Column(String(50), nullable=False)
    span_name = Column(String(100), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    request_data = Column(Text, nullable=True)
    response_data = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    client_id = Column(String(36), nullable=True)
    api_path = Column(String(200), nullable=True)
    create_time = Column(DateTime, default=func.current_timestamp(), nullable=False)