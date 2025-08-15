import httpx
from typing import Dict
from fastapi import HTTPException
from loguru import logger

# 外部接口地址
EXTERNAL_API_URL = "http://210.12.11.251:27861/api/signals/v1/submit"


async def call_recommend_api(request_data: Dict):
    """调用外部推荐接口的FastAPI端点"""
    logger.bind(name="app.services.test_net_assistant").info(
        f"🚀 开始调用外部AI推荐接口: URL={EXTERNAL_API_URL}"
    )
    logger.bind(name="app.services.test_net_assistant").info(
        f"📤 请求数据: {request_data}"
    )
    
    try:
        # 使用httpx异步客户端发送请求，设置10秒超时
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 发送POST请求
            response = await client.post(
                EXTERNAL_API_URL,
                json=request_data,  # 直接使用字典数据
                headers={
                    "accept": "*/*",
                    "Content-Type": "application/json"
                }
            )

            # 检查响应状态码
            response.raise_for_status()  # 如果状态码是4xx或5xx会抛出异常
            
            # 记录响应状态和内容长度
            logger.bind(name="app.services.test_net_assistant").info(
                f"📊 响应状态: status_code={response.status_code}, content_length={len(response.content)}"
            )
            
            # 检查响应内容是否为空
            if not response.content:
                logger.bind(name="app.services.test_net_assistant").warning(
                    "⚠️ 外部API返回空响应内容"
                )
                return {
                    "status": "success",
                    "data": {"message": "外部API返回空响应"}
                }
            
            # 记录原始响应内容（前200字符用于调试）
            content_preview = response.text[:200] if len(response.text) > 200 else response.text
            logger.bind(name="app.services.test_net_assistant").info(
                f"📄 响应内容预览: {content_preview}"
            )
            
            # 尝试解析JSON响应
            try:
                response_data = response.json()
                logger.bind(name="app.services.test_net_assistant").info(
                    f"✅ AI推荐接口调用成功: status_code={response.status_code}"
                )
                logger.bind(name="app.services.test_net_assistant").info(
                    f"📥 响应数据: {response_data}"
                )
            except ValueError as json_error:
                logger.bind(name="app.services.test_net_assistant").error(
                    f"❌ JSON解析失败: {str(json_error)}, 响应内容: {response.text}"
                )
                return {
                    "status": "success",
                    "data": {
                        "message": "外部API返回非JSON格式响应",
                        "raw_response": response.text
                    }
                }

            # 返回外部接口的响应结果
            return {
                "status": "success",
                "data": response_data
            }

    except httpx.HTTPError as e:
        # 处理HTTP相关错误
        logger.bind(name="app.services.test_net_assistant").error(
            f"❌ HTTP请求失败: {str(e)}, URL={EXTERNAL_API_URL}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"调用外部接口失败: {str(e)}"
        )
    except Exception as e:
        # 处理其他异常
        logger.bind(name="app.services.test_net_assistant").error(
            f"❌ 调用外部接口异常: {str(e)}, 请求数据: {request_data}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生错误: {str(e)}"
        )