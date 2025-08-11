"""
HIS推送接口实现
符合CDSS标准的患者病历信息接收接口
POST /api/CHKR01/rest/
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json
from datetime import datetime
from loguru import logger

from app.core.database import get_database
from app.core.config import settings
from app.schemas.his_schemas import CDSSMessage, HisPushResponse, HisPushResponseData
from app.models.database_models import HisPushLog
from app.services.his_service import HisService
from app.services.websocket_service import WebSocketService

router = APIRouter()


@router.post("/CHKR01/rest/", response_model=HisPushResponse)
async def receive_his_push(
    cdss_message: CDSSMessage,
    request: Request,
    db: AsyncSession = Depends(get_database),
    # CDSS标准请求头（使用alias支持下划线格式）
    hospital_id: str = Header(..., alias="hospital_id", description="医疗机构编码"),
    service_id: str = Header(..., alias="service_id", description="服务ID"),
    visit_type: str = Header(..., alias="visit_type", description="就诊类型编码"),
    send_sys_id: str = Header(..., alias="send_sys_id", description="发送系统ID"),
    apply_unit_id: str = Header(default="0", alias="apply_unit_id", description="申请科室编码"),
    exec_unit_id: str = Header(default="0", alias="exec_unit_id", description="执行科室编码"),
    order_exec_id: str = Header(default="0", alias="order_exec_id", description="执行ID"),
    extend_sub_id: str = Header(default="AI_REC", alias="extend_sub_id", description="扩展类型")
):
    """
    接收HIS系统推送的患者及病历信息
    符合首都医科大学附属友谊医院CDSS服务接口标准
    """
    
    # 生成消息ID
    message_id = f"his_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    
    try:
        logger.info(f"🏥 收到HIS推送: message_id={message_id}, pat_no={cdss_message.patNo}")
        
        # 1. 验证请求头
        if service_id != settings.HIS_SERVICE_ID:
            logger.error(f"❌ service_id不匹配: 期望={settings.HIS_SERVICE_ID}, 实际={service_id}")
            raise HTTPException(
                status_code=400,
                detail={"code": 1001, "message": "service_id不匹配", "error": f"期望{settings.HIS_SERVICE_ID}"}
            )
        
        # 2. 验证场景类型
        if cdss_message.sceneType != settings.HIS_SCENE_TYPE:
            logger.error(f"❌ sceneType不匹配: 期望={settings.HIS_SCENE_TYPE}, 实际={cdss_message.sceneType}")
            raise HTTPException(
                status_code=400,
                detail={"code": 1002, "message": "sceneType不匹配", "error": f"期望{settings.HIS_SCENE_TYPE}"}
            )
        
        # 3. 验证必填字段
        required_fields = ['systemId', 'patNo', 'patName', 'admId', 'visitType']
        for field in required_fields:
            if not getattr(cdss_message, field, None):
                logger.error(f"❌ 必填字段缺失: {field}")
                raise HTTPException(
                    status_code=400,
                    detail={"code": 1003, "message": "必填字段缺失", "error": f"{field}字段不能为空"}
                )
        
        # 4. 验证itemData格式
        item_data = cdss_message.itemData
        required_item_fields = ['patientAge', 'patientSex', 'clinicInfo', 'abstractHistory']
        for field in required_item_fields:
            if not getattr(item_data, field, None):
                logger.error(f"❌ itemData字段缺失: {field}")
                raise HTTPException(
                    status_code=400,
                    detail={"code": 1004, "message": "itemData格式错误", "error": f"{field}字段不能为空"}
                )
        
        # 5. 初始化服务
        his_service = HisService(db)
        websocket_service = WebSocketService()
        
        # 6. 查找关联的客户端
        client_id = await his_service.find_client_by_user_info(
            cdss_message.userIP, 
            cdss_message.userCode
        )
        
        if not client_id:
            logger.warning(f"⚠️ 未找到关联客户端: userIP={cdss_message.userIP}, userCode={cdss_message.userCode}")
            # 不抛出异常，仍然记录日志，但标记为客户端未找到
        
        # 7. 保存HIS推送记录
        his_log = await his_service.save_his_push_log(
            message_id=message_id,
            cdss_message=cdss_message,
            client_id=client_id,
            headers={
                "hospital_id": hospital_id,
                "service_id": service_id,
                "visit_type": visit_type,
                "send_sys_id": send_sys_id,
                "apply_unit_id": apply_unit_id,
                "exec_unit_id": exec_unit_id,
                "order_exec_id": order_exec_id,
                "extend_sub_id": extend_sub_id
            }
        )
        
        # 8. 如果找到客户端，通过WebSocket推送消息
        if client_id:
            try:
                await websocket_service.push_patient_data(client_id, cdss_message, message_id)
                logger.info(f"✅ WebSocket推送成功: client_id={client_id}")
            except Exception as ws_error:
                logger.error(f"❌ WebSocket推送失败: {ws_error}")
                # 更新推送状态
                await his_service.update_push_status(his_log.id, "websocket_failed", str(ws_error))
        
        # 9. 返回成功响应
        response_data = HisPushResponseData(
            messageId=message_id,
            timestamp=datetime.now().isoformat(),
            processStatus="received"
        )
        
        logger.info(f"✅ HIS推送处理完成: message_id={message_id}")
        
        return HisPushResponse(
            code=200,
            message="消息接收成功",
            data=response_data.dict()
        )
        
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"❌ HIS推送处理异常: {e}")
        
        # 记录异常日志
        try:
            his_service = HisService(db)
            await his_service.log_system_error(
                module="his_push",
                operation="receive_his_push",
                message=f"处理异常: {str(e)}",
                details={"message_id": message_id, "error": str(e)}
            )
        except:
            pass
        
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "服务器内部错误", "error": "处理请求时发生异常"}
        )