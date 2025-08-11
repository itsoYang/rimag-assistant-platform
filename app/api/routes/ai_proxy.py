"""
AI服务代理接口实现
为客户端提供AI推荐服务的代理
POST /api/ai/recommend
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from datetime import datetime
from loguru import logger

from app.core.database import get_database
from app.schemas.ai_schemas import AiProxyRequest, AiProxyResponse, AiProxyResponseData
from app.services.ai_service import AiService
from app.services.his_service import HisService
from app.services.websocket_service import WebSocketService
from app.models.database_models import HisPushLog
from sqlalchemy import select, and_

router = APIRouter()


@router.post("/ai/recommend", response_model=AiProxyResponse)
async def ai_recommend_proxy(
    request: AiProxyRequest,
    db: AsyncSession = Depends(get_database)
):
    """
    AI推荐服务代理接口
    客户端通过此接口获取AI推荐结果
    """
    
    try:
        logger.info(f"🎯 收到AI推荐请求: request_id={request.request_id}, client_id={request.client_id}")
        
        # 1. 验证请求参数
        if not request.client_id or not request.doctor_id or not request.request_id:
            raise HTTPException(
                status_code=400,
                detail={"code": 400, "message": "请求参数不完整", "error": "client_id, doctor_id, request_id为必填字段"}
            )
        
        # 2. 初始化服务
        ai_service = AiService(db)
        his_service = HisService(db)
        websocket_service = WebSocketService()
        
        # 3. 检查是否使用缓存数据
        if request.use_cached_data:
            cached_recommendations = await ai_service.get_cached_recommendation(
                request.patient_id, 
                request.visit_id
            )
            if cached_recommendations:
                logger.info(f"📋 返回缓存推荐: request_id={request.request_id}")
                
                response_data = AiProxyResponseData(
                    request_id=request.request_id,
                    recommendations=cached_recommendations,
                    total_count=len(cached_recommendations),
                    processing_time=0.1,  # 缓存响应时间很快
                    ai_service="rimagai_checkitem",
                    session_id=request.visit_id
                )
                
                return AiProxyResponse(
                    code=200,
                    message="AI推荐获取成功（缓存）",
                    data=response_data.dict()
                )
        
        # 4. 查找最近的HIS推送记录
        his_push_log = await _find_recent_his_push_log(db, request.patient_id, request.visit_id, request.doctor_id)
        
        if not his_push_log:
            logger.error(f"❌ 未找到HIS推送记录: patient_id={request.patient_id}, visit_id={request.visit_id}")
            raise HTTPException(
                status_code=404,
                detail={"code": 404, "message": "未找到患者病历数据", "error": "请确保HIS系统已推送患者信息"}
            )
        
        # 5. 构造CDSS消息（从HIS推送记录重建）
        cdss_message = await _rebuild_cdss_message_from_log(his_push_log)
        
        # 6. 调用AI推荐服务
        try:
            recommendations = await ai_service.call_ai_recommendation(
                cdss_message=cdss_message,
                request_id=request.request_id,
                client_id=request.client_id,
                his_push_log_id=his_push_log.id
            )

            logger.info(f"AI服务-检查项目推荐调用成功，返回结果：{recommendations}")
            
            # 7. 通过WebSocket推送结果给客户端（异步）
            try:
                await websocket_service.push_ai_recommendation(
                    client_id=request.client_id,
                    request_id=request.request_id,
                    recommendations=[rec.dict() for rec in recommendations],
                    processing_time=0.0  # 这里会在AI服务中计算
                )
            except Exception as ws_error:
                logger.warning(f"⚠️ WebSocket推送失败，但API仍返回结果: {ws_error}")
            
            # 8. 构造响应
            response_data = AiProxyResponseData(
                request_id=request.request_id,
                recommendations=recommendations,
                total_count=len(recommendations),
                processing_time=0.0,  # 实际时间在AI服务日志中
                ai_service="rimagai_checkitem",
                session_id=cdss_message.admId
            )
            
            logger.info(f"✅ AI推荐处理完成: request_id={request.request_id}, count={len(recommendations)}")
            
            return AiProxyResponse(
                code=200,
                message="AI推荐获取成功",
                data=response_data.dict()
            )
            
        except Exception as ai_error:
            logger.error(f"❌ AI服务调用失败: {ai_error}")
            raise HTTPException(
                status_code=500,
                detail={"code": 500, "message": "AI推荐服务调用失败", "error": str(ai_error)}
            )
    
    except HTTPException:
        # 重新抛出HTTP异常
        raise
    except Exception as e:
        logger.error(f"❌ AI代理接口异常: {e}")
        
        # 记录系统错误
        try:
            his_service = HisService(db)
            await his_service.log_system_error(
                module="ai_proxy",
                operation="ai_recommend_proxy",
                message=f"处理异常: {str(e)}",
                details={"request_id": request.request_id, "error": str(e)},
                client_id=request.client_id,
                request_id=request.request_id
            )
        except:
            pass
        
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "服务器内部错误", "error": "处理请求时发生异常"}
        )


async def _find_recent_his_push_log(db: AsyncSession, patient_id: str, visit_id: str, doctor_id: str) -> HisPushLog:
    """查找最近的HIS推送记录"""
    try:
        from datetime import datetime, timedelta
        
        # 查询最近30分钟内的HIS推送记录
        query = select(HisPushLog).where(
            and_(
                HisPushLog.pat_no == patient_id,
                HisPushLog.adm_id == visit_id,
                HisPushLog.user_code == doctor_id,
                HisPushLog.push_status == "success",
                HisPushLog.created_at >= datetime.now() - timedelta(minutes=30)
            )
        ).order_by(HisPushLog.created_at.desc())
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"❌ 查找HIS推送记录失败: {e}")
        return None


async def _rebuild_cdss_message_from_log(his_log: HisPushLog):
    """从HIS推送日志重建CDSS消息"""
    try:
        from app.schemas.his_schemas import CDSSMessage, ItemData
        import json
        
        # 解析itemData
        item_data_dict = json.loads(his_log.item_data) if his_log.item_data else {}
        item_data = ItemData(**item_data_dict)
        
        # 重建CDSS消息
        cdss_message = CDSSMessage(
            systemId=his_log.system_id,
            sceneType=his_log.scene_type,
            state=his_log.state,
            patNo=his_log.pat_no,
            patName=his_log.pat_name,
            admId=his_log.adm_id,
            visitType=his_log.visit_type,
            deptCode=his_log.dept_code,
            deptDesc=his_log.dept_desc,
            hospCode=his_log.hosp_code,
            hospDesc=his_log.hosp_desc,
            userIP=his_log.user_ip,
            userCode=his_log.user_code,
            userName=his_log.user_name,
            msgTime=his_log.msg_time.strftime("%Y-%m-%d %H:%M:%S") if his_log.msg_time else "",
            remark=his_log.remark or "",
            itemData=item_data
        )
        
        return cdss_message
        
    except Exception as e:
        logger.error(f"❌ 重建CDSS消息失败: {e}")
        raise Exception(f"重建患者病历数据失败: {e}")