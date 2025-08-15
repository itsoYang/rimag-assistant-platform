from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from typing import Optional, Dict, Any
import json
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AiService
from app.services.websocket_service import WebSocketManager
from app.core.trace import TraceManager
from app.core.database import get_database
from app.schemas.ai_schemas import AiRecommendationRequest, AiRecommendationResponse


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI代理"])

# WebSocket管理器实例
websocket_manager = WebSocketManager()


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket连接端点，用于实时推送AI推荐结果
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端唯一标识
    """
    await websocket_manager.connect(websocket, client_id)
    logger.info(f"客户端 {client_id} 已连接WebSocket")
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 处理不同类型的消息
            message_type = message.get("type")
            
            if message_type == "ai_recommendation":
                await handle_ai_recommendation_request(websocket, client_id, message)
            elif message_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()}))
            else:
                logger.warning(f"未知消息类型: {message_type}")
                
    except WebSocketDisconnect:
        logger.info(f"客户端 {client_id} 断开WebSocket连接")
    except Exception as e:
        logger.error(f"WebSocket连接异常: {str(e)}")
    finally:
        websocket_manager.disconnect(client_id)


async def handle_ai_recommendation_request(websocket: WebSocket, client_id: str, message: Dict[str, Any]):
    """
    处理AI推荐请求
    
    Args:
        websocket: WebSocket连接对象
        client_id: 客户端ID
        message: 请求消息
    """
    try:
        # 提取请求参数
        request_data = message.get("data", {})
        trace_id = message.get("trace_id")
        
        # 生成Trace ID（如果未提供）
        if not trace_id:
            trace_id = TraceManager.generate_trace_id()
        
        # 构造AI推荐请求
        ai_request = AiRecommendationRequest(
            patient_id=request_data.get("patient_id"),
            patient_name=request_data.get("patient_name"),
            diagnose_name=request_data.get("diagnose_name"),
            his_data=request_data.get("his_data", {}),
            client_id=client_id,
            trace_id=trace_id
        )
        
        # 发送开始处理消息
        await websocket.send_text(json.dumps({
            "type": "ai_recommendation_start",
            "trace_id": trace_id,
            "timestamp": datetime.now().isoformat()
        }))
        
        # 调用AI服务进行流式推荐
        ai_service = AiService()
        await ai_service.call_ai_recommendation_streaming(
            request=ai_request,
            websocket_manager=websocket_manager,
            client_id=client_id
        )
        
    except Exception as e:
        logger.error(f"处理AI推荐请求失败: {str(e)}")
        # 发送错误消息
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"AI推荐请求处理失败: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }))


@router.post("/recommendation", response_model=AiRecommendationResponse)
async def get_ai_recommendation(
    request: AiRecommendationRequest,
    db: AsyncSession = Depends(get_database)
):
    """
    获取AI推荐（同步接口）
    
    Args:
        request: AI推荐请求
        
    Returns:
        AI推荐响应
    """
    try:
        # 生成Trace ID
        trace_id = TraceManager.generate_trace_id()
        request.trace_id = trace_id
        
        # 调用AI服务
        ai_service = AiService(db)
        # 从请求中构造CDSSMessage（简化版本用于测试）
        from app.schemas.his_schemas import CDSSMessage, ItemData
        from datetime import datetime
        
        # 构造ItemData
        item_data = ItemData(
            patientAge=request.patient_age or "unknown",
            patientSex=request.patient_sex or "unknown",
            clinicInfo=request.clinic_info or "",
            abstractHistory=request.abstract_history or ""
        )
        
        # 构造CDSSMessage
        cdss_message = CDSSMessage(
            systemId="TEST_SYSTEM",
            patNo=request.patient_id,
            patName="测试患者",
            admId=request.session_id or "test-session",
            visitType="03",  # 门诊
            deptCode=request.department or "unknown",
            deptDesc=request.department or "unknown",
            userIP="127.0.0.1",
            userCode=request.doctor_id or "unknown",
            userName="测试医生",
            msgTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            itemData=item_data
        )
        
        # 生成request_id和client_id
        import uuid
        request_id = str(uuid.uuid4())
        client_id = getattr(request, 'client_id', 'api_client')
        
        result = await ai_service.call_ai_recommendation(
            cdss_message=cdss_message,
            request_id=request_id,
            client_id=client_id
        )
        
        return AiRecommendationResponse(
            code=0,
            message="AI推荐获取成功",
            session_id=request.session_id,
            recommendations=result if isinstance(result, list) else [],
            total_count=len(result) if isinstance(result, list) else 0,
            processing_time=0.0,
            finish=True,
            partial=False
        )
        
    except Exception as e:
        logger.error(f"获取AI推荐失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI推荐服务异常: {str(e)}")


@router.get("/recommendation/cache/{session_id}")
async def get_cached_recommendation(
    session_id: str,
    db: AsyncSession = Depends(get_database)
):
    """
    获取缓存的AI推荐结果
    
    Args:
        session_id: 会话ID
        
    Returns:
        缓存的推荐结果
    """
    try:
        ai_service = AiService(db)
        result = await ai_service.get_cached_recommendation(session_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="未找到缓存的推荐结果")
            
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取缓存推荐失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取缓存失败: {str(e)}")


@router.get("/health")
async def health_check():
    """
    健康检查接口
    
    Returns:
        服务状态
    """
    return {
        "status": "healthy",
        "service": "ai-proxy",
        "timestamp": datetime.now().isoformat()
    }