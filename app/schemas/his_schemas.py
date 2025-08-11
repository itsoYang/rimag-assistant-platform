"""
HIS推送接口相关的Pydantic模型
符合CDSS标准的数据结构定义
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ItemData(BaseModel):
    """场景数据（检查项目推荐）"""
    patientAge: str = Field(..., description="患者年龄")
    patientSex: str = Field(..., description="患者性别")
    clinicInfo: str = Field(..., description="主诉信息")
    abstractHistory: str = Field(..., description="病史摘要")


class CDSSMessage(BaseModel):
    """CDSS消息框架"""
    systemId: str = Field(..., description="系统ID")
    sceneType: str = Field(default="EXAM001", description="场景类型")
    state: int = Field(default=0, description="状态（0:新增,1:更新,-1:撤销）")
    patNo: str = Field(..., description="患者登记号")
    patName: str = Field(..., description="患者姓名")
    admId: str = Field(..., description="就诊流水号")
    visitType: str = Field(..., description="就诊类型")
    deptCode: Optional[str] = Field(None, description="科室代码")
    deptDesc: Optional[str] = Field(None, description="科室名称")
    hospCode: Optional[str] = Field(None, description="院区代码")
    hospDesc: Optional[str] = Field(None, description="院区名称")
    userIP: str = Field(..., description="客户端IP地址")
    userCode: str = Field(..., description="用户代码")
    userName: Optional[str] = Field(None, description="用户名称")
    msgTime: str = Field(..., description="消息时间")
    remark: Optional[str] = Field("", description="备注")
    itemData: ItemData = Field(..., description="场景数据")


class HisHeaders(BaseModel):
    """HIS推送请求头"""
    hospital_id: str = Field(default="400688609-7", description="医疗机构编码")
    service_id: str = Field(default="CHKR01", description="服务ID")
    visit_type: str = Field(default="门诊", description="就诊类型编码")
    apply_unit_id: Optional[str] = Field("0", description="申请科室编码")
    exec_unit_id: Optional[str] = Field("0", description="执行科室编码")
    send_sys_id: str = Field(default="400688609-8", description="发送系统ID")
    order_exec_id: Optional[str] = Field("0", description="执行ID")
    extend_sub_id: Optional[str] = Field("AI_REC", description="场景类型")


class HisPushRequest(BaseModel):
    """HIS推送请求"""
    headers: HisHeaders
    body: CDSSMessage


class HisPushResponse(BaseModel):
    """HIS推送响应"""
    code: int = Field(..., description="响应码")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    error: Optional[str] = Field(None, description="错误信息")


class HisPushResponseData(BaseModel):
    """HIS推送响应数据"""
    messageId: str = Field(..., description="消息ID")
    timestamp: str = Field(..., description="时间戳")
    processStatus: str = Field(..., description="处理状态")


class PatientSummary(BaseModel):
    """患者信息摘要（用于WebSocket推送）"""
    patNo: str = Field(..., description="患者登记号")
    patName: str = Field(..., description="患者姓名")
    admId: str = Field(..., description="就诊流水号")
    deptCode: str = Field(..., description="科室代码")
    deptDesc: str = Field(..., description="科室名称")
    userCode: str = Field(..., description="用户代码")
    userName: str = Field(..., description="用户名称")
    patientInfo: ItemData = Field(..., description="患者详细信息")