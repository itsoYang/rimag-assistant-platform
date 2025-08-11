"""
AI服务相关的Pydantic模型
外部AI服务接口和内部代理接口的数据结构定义
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class PatientInfoRequest(BaseModel):
    """AI服务请求参数（外部接口）"""
    session_id: str = Field(..., description="会话ID")
    patient_id: str = Field(..., description="患者ID")
    doctor_id: str = Field(..., description="医生ID")
    department: str = Field(..., description="科室")
    source: str = Field(default="lip", description="来源")
    patient_sex: str = Field(..., description="患者性别")
    patient_age: str = Field(..., description="患者年龄")
    abstract_history: str = Field(..., description="病史摘要")
    clinic_info: str = Field(..., description="主诉")
    recommend_count: int = Field(default=3, description="推荐项目数量")
    # 根据最新服务校验错误，新增必传字段（初步诊断/疑似诊断）
    diagnose_name: str = Field(default="", description="诊断名称/疑似诊断")


class CheckItemWithReasonResponse(BaseModel):
    """AI服务响应数据结构"""
    code: int = Field(..., description="返回码，0表示成功，非0表示失败")
    message: str = Field(..., description="返回信息")
    finish: bool = Field(..., description="是否结束，True表示结束")
    data: Optional[Dict[str, str]] = Field(None, description="返回数据")


class AiRecommendationResult(BaseModel):
    """AI推荐结果（内部处理后）"""
    check_item_name: str = Field(..., description="检查项目名称")
    reason: str = Field(..., description="推荐理由")
    cautions: str = Field(..., description="注意事项")
    sequence: int = Field(..., description="序号")


class AiProxyRequest(BaseModel):
    """AI代理接口请求"""
    client_id: str = Field(..., description="客户端ID")
    doctor_id: str = Field(..., description="医生ID")
    request_id: str = Field(..., description="请求ID")
    patient_id: str = Field(..., description="患者ID")
    visit_id: str = Field(..., description="就诊ID")
    use_cached_data: bool = Field(default=True, description="是否使用缓存的患者数据")
    recommendation_type: str = Field(default="examination", description="推荐类型")
    max_results: int = Field(default=10, description="最大结果数")
    min_confidence: float = Field(default=0.6, description="最小置信度")


class AiProxyResponse(BaseModel):
    """AI代理接口响应"""
    code: int = Field(..., description="响应码")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")
    error: Optional[str] = Field(None, description="错误信息")


class AiProxyResponseData(BaseModel):
    """AI代理响应数据"""
    request_id: str = Field(..., description="请求ID")
    recommendations: List[AiRecommendationResult] = Field(..., description="推荐列表")
    total_count: int = Field(..., description="总数量")
    processing_time: float = Field(..., description="处理时间（秒）")
    ai_service: str = Field(..., description="AI服务名称")
    session_id: str = Field(..., description="会话ID")


class AiServiceConfig(BaseModel):
    """AI服务配置"""
    base_url: str = Field(..., description="基础URL")
    endpoint: str = Field(..., description="接口路径")
    timeout: int = Field(default=30, description="超时时间（秒）")
    default_source: str = Field(default="lip", description="默认来源")
    default_recommend_count: int = Field(default=3, description="默认推荐数量")