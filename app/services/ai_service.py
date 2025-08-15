"""
AI服务调用相关业务服务
处理外部AI推荐服务的调用和数据转换
"""

import httpx
import json
import time
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.schemas.ai_schemas import PatientInfoRequest, AiRecommendationResult
from app.schemas.his_schemas import CDSSMessage
from app.models.database_models import (
    AiRecommendationLog,
    SystemLog,
    ServiceCall,
    AiSession,
    AiSessionRecord,
)
from app.services.websocket_service import WebSocketService
from app.services.trace_service import create_trace, create_span, finish_span


class AiService:
    """AI服务调用管理"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = settings.AI_SERVICE_BASE_URL
        self.endpoint = settings.AI_SERVICE_ENDPOINT
        self.timeout = settings.AI_SERVICE_TIMEOUT
    
    async def call_ai_recommendation(
        self, 
        cdss_message: CDSSMessage, 
        request_id: str,
        client_id: str,
        his_push_log_id: Optional[str] = None
    ) -> List[AiRecommendationResult]:
        """
        调用外部AI推荐服务
        处理流式响应并返回结构化结果
        """
        
        start_time = time.time()
        
        try:
            logger.bind(name="app.services.ai_service").info(f"🤖 开始调用AI服务: request_id={request_id}")
            
            # 1. 构造AI服务请求参数
            ai_request = self._build_ai_request(cdss_message, request_id)
            
            # 2. 调用AI服务
            recommendations = await self._call_external_ai_service(ai_request)
            
            # 3. 计算处理时间
            processing_time = round(time.time() - start_time, 2)
            
            # 4. 保存AI推荐日志
            await self._save_ai_recommendation_log(
                request_id=request_id,
                client_id=client_id,
                cdss_message=cdss_message,
                his_push_log_id=his_push_log_id,
                ai_request_data=ai_request.dict(),
                recommendations=recommendations,
                processing_time=processing_time,
                status="success"
            )
            
            logger.bind(name="app.services.ai_service").info(
                f"✅ AI推荐调用成功: request_id={request_id}, count={len(recommendations)}, time={processing_time}s"
            )
            
            return recommendations
            
        except Exception as e:
            processing_time = round(time.time() - start_time, 2)
            logger.bind(name="app.services.ai_service").error(
                f"❌ AI推荐调用失败: request_id={request_id}, error={e}"
            )
            
            # 保存失败日志
            try:
                await self._save_ai_recommendation_log(
                    request_id=request_id,
                    client_id=client_id,
                    cdss_message=cdss_message,
                    his_push_log_id=his_push_log_id,
                    ai_request_data=None,
                    recommendations=[],
                    processing_time=processing_time,
                    status="failed",
                    error_message=str(e)
                )
            except:
                pass
            
            raise

    async def call_ai_recommendation_streaming(
        self,
        cdss_message: CDSSMessage,
        request_id: str,
        client_id: str,
        websocket_service: WebSocketService,
        his_push_log_id: Optional[str] = None,
    ) -> List[AiRecommendationResult]:
        """调用外部AI推荐服务（边解析边通过WebSocket推送增量结果）"""
        start_time = time.time()

        # 累积结构：{ check_item_name: { reason: str, cautions: str } }
        recommendations_dict: Dict[str, Dict[str, str]] = {}

        try:
            # Trace & Span 开始
            trace_id = await create_trace(self.db, request_id=request_id, client_id=client_id)
            span_ai = await create_span(self.db, trace_id, name="ai_stream_call", service_name="Assistant-Server", api_path=self.endpoint)
            ai_request = self._build_ai_request(cdss_message, request_id)

            url = f"{self.base_url}{self.endpoint}"
            logger.bind(name="app.services.ai_service").info(
                f"🤖 [AI-STREAM] 请求流式AI: url={url}, request_id={request_id}"
            )
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=ai_request.dict(),
                    headers={
                        "Accept": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Accept-Encoding": "identity",
                        "Content-Type": "application/json",
                    }
                ) as response:
                    logger.bind(name="app.services.ai_service").info(
                        f"🤖 [AI-STREAM] 响应: status={response.status_code}, headers={dict(response.headers)}"
                    )
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "").lower()
                    seen_any_chunk = False

                    # 非SSE：直接整包JSON，做一次性解析（大概率是参数校验失败或服务降级返回JSON）
                    if "text/event-stream" not in content_type and "application/json" in content_type:
                        raw = await response.aread()
                        try:
                            j = json.loads(raw.decode(errors="ignore"))
                        except Exception:
                            j = None
                        logger.bind(name="app.services.ai_service").info(
                            f"🤖 [AI-STREAM][JSON] body(<=500): {raw[:500]!r}"
                        )
                        if isinstance(j, dict):
                            # 若返回错误码，立即推送错误并结束（避免前端长时间等待）
                            if isinstance(j.get("code"), int) and j.get("code") != 0:
                                err_msg = str(j.get("message") or j)
                                await websocket_service.manager.send_error(
                                    client_id,
                                    "AI_JSON_ERROR",
                                    "AI服务返回错误",
                                    err_msg,
                                )
                                # 直接返回空列表，由上层统一推送finish
                                recommendations_dict.clear()
                            
                            # 兜底提取：data 为数组；或 data/recommendations/result 内有数组
                            candidates = []
                            if isinstance(j.get("data"), list):
                                candidates = j.get("data", [])
                            elif isinstance(j.get("data"), dict):
                                d = j.get("data")
                                for k in ["recommendations", "items", "results", "list"]:
                                    if isinstance(d.get(k), list):
                                        candidates = d.get(k)
                                        break
                            elif isinstance(j.get("recommendations"), list):
                                candidates = j.get("recommendations")

                            for idx, it in enumerate(candidates, 1):
                                if not isinstance(it, dict):
                                    continue
                                name = it.get("check_item_name") or it.get("checkItemName")
                                if not name:
                                    continue
                                reason = it.get("reason", "")
                                cautions = it.get("cautions", "")
                                recommendations_dict[name] = {
                                    "reason": str(reason),
                                    "cautions": str(cautions),
                                }
                        # 跳过后续按行解析
                    else:
                        async for line in response.aiter_lines():
                            # 诊断日志（限制长度，避免刷屏）
                            if line is not None:
                                logger.bind(name="app.services.ai_service").info(
                                    f"🤖 [AI-STREAM] line: {str(line)[:200]}"
                                )
                            if not line:
                                continue
                            data_line = line.lstrip()
                            # 支持 data: 前缀；如无此前缀且是JSON也尝试解析
                            if data_line.startswith("data:"):
                                data_str = data_line[5:].strip()
                            else:
                                data_str = data_line if data_line.startswith("{") else ""
                            if not data_str:
                                continue
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            # 结束信号
                            if isinstance(data, dict) and data.get("finish") in (1, True, "true", "True"):
                                break

                            payload = None
                            if isinstance(data, dict) and data.get("code") == 0 and isinstance(data.get("data"), dict):
                                payload = data["data"]
                            elif isinstance(data, dict) and (
                                "check_item_name" in data or "reason" in data or "cautions" in data
                            ):
                                payload = data

                            if isinstance(payload, dict):
                                name = payload.get("check_item_name", "")
                                reason = payload.get("reason", "")
                                cautions = payload.get("cautions", "")
                                if not name:
                                    continue

                                if name not in recommendations_dict:
                                    recommendations_dict[name] = {"reason": "", "cautions": ""}

                                # 累积拼接
                                recommendations_dict[name]["reason"] += str(reason)
                                recommendations_dict[name]["cautions"] += str(cautions)

                                # 构建当前快照并推送 partial
                                current_list: List[AiRecommendationResult] = []
                                for i, (n, agg) in enumerate(recommendations_dict.items(), 1):
                                    current_list.append(AiRecommendationResult(
                                        check_item_name=n,
                                        reason=agg["reason"].strip(),
                                        cautions=agg["cautions"].strip(),
                                        sequence=i
                                    ))

                                elapsed = round(time.time() - start_time, 2)
                                await websocket_service.push_ai_recommendation(
                                    client_id=client_id,
                                    request_id=request_id,
                                    recommendations=[rec.dict() for rec in current_list],
                                    processing_time=elapsed,
                                    pat_no=cdss_message.patNo,
                                    partial=True,
                                    finish=False,
                                )
                                seen_any_chunk = True

            # 最终结果
            final_list: List[AiRecommendationResult] = []
            for i, (n, agg) in enumerate(recommendations_dict.items(), 1):
                final_list.append(AiRecommendationResult(
                    check_item_name=n,
                    reason=agg["reason"].strip(),
                    cautions=agg["cautions"].strip(),
                    sequence=i
                ))

            total_time = round(time.time() - start_time, 2)

            # 推送完成
            await websocket_service.push_ai_recommendation(
                client_id=client_id,
                request_id=request_id,
                recommendations=[rec.dict() for rec in final_list],
                processing_time=total_time,
                pat_no=cdss_message.patNo,
                partial=False,
                finish=True,
            )

            # 若未命中任何分片，发一条错误提示，方便前端可视化问题
            if not final_list:
                try:
                    await websocket_service.manager.send_error(
                        client_id,
                        "AI_STREAM_EMPTY",
                        "AI流未返回推荐分片或分片格式不匹配",
                        "请检查外部AI服务返回的流式数据格式与字段"
                    )
                except Exception:
                    pass

            # 落库日志
            try:
                await self._save_ai_recommendation_log(
                    request_id=request_id,
                    client_id=client_id,
                    cdss_message=cdss_message,
                    his_push_log_id=his_push_log_id,
                    ai_request_data=self._build_ai_request(cdss_message, request_id).dict(),
                    recommendations=final_list,
                    processing_time=total_time,
                    status="success",
                )
            except Exception:
                pass

            # 会话聚合落库
            try:
                session_id = await self._ensure_ai_session(
                    patient_id=cdss_message.patNo,
                    visit_id=cdss_message.admId,
                    doctor_id=cdss_message.userCode,
                )
                await self._append_ai_session_record(session_id=session_id, request_id=request_id, summary=None)
            except Exception:
                pass

            # 记录服务调用成功
            try:
                await self._save_service_call(
                    request_id=request_id,
                    client_id=client_id,
                    status="success",
                    duration_ms=int(total_time * 1000),
                )
            except Exception:
                pass

            # 收尾 Trace/Span
            try:
                await finish_span(self.db, span_ai, status="SUCCESS", response={"count": len(final_list)})
            except Exception:
                pass

            return final_list

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            # 失败也通知前端完成（空结果）
            try:
                await websocket_service.push_ai_recommendation(
                    client_id=client_id,
                    request_id=request_id,
                    recommendations=[],
                    processing_time=elapsed,
                    pat_no=cdss_message.patNo,
                    partial=False,
                    finish=True,
                )
            except Exception:
                pass

            # 记录失败日志
            try:
                await self._save_ai_recommendation_log(
                    request_id=request_id,
                    client_id=client_id,
                    cdss_message=cdss_message,
                    his_push_log_id=his_push_log_id,
                    ai_request_data=None,
                    recommendations=[],
                    processing_time=elapsed,
                    status="failed",
                    error_message=str(e),
                )
            except Exception:
                pass

            # 会话聚合落库（失败也记录到会话）
            try:
                session_id = await self._ensure_ai_session(
                    patient_id=cdss_message.patNo,
                    visit_id=cdss_message.admId,
                    doctor_id=cdss_message.userCode,
                )
                await self._append_ai_session_record(session_id=session_id, request_id=request_id, summary=str(e))
            except Exception:
                pass

            # 记录服务调用失败
            try:
                await self._save_service_call(
                    request_id=request_id,
                    client_id=client_id,
                    status="failed",
                    duration_ms=int(elapsed * 1000),
                    error_message=str(e),
                )
            except Exception:
                pass

            # 收尾 Trace/Span（失败）
            try:
                # 若上文创建 span_ai 失败，忽略
                if 'span_ai' in locals():
                    await finish_span(self.db, span_ai, status="FAILED", error_message=str(e))
            except Exception:
                pass

            raise
    
    def _build_ai_request(self, cdss_message: CDSSMessage, request_id: str) -> PatientInfoRequest:
        """构造AI服务请求参数"""
        
        return PatientInfoRequest(
            session_id=cdss_message.admId,  # 使用就诊流水号作为会话ID
            patient_id=cdss_message.patNo,  # 患者登记号
            doctor_id=cdss_message.userCode,  # 医生ID
            department=cdss_message.deptCode or "unknown",  # 科室代码
            source=settings.AI_DEFAULT_SOURCE,  # 默认来源
            patient_sex=cdss_message.itemData.patientSex,  # 患者性别
            patient_age=cdss_message.itemData.patientAge,  # 患者年龄
            abstract_history=cdss_message.itemData.abstractHistory,  # 病史摘要
            clinic_info=cdss_message.itemData.clinicInfo,  # 主诉信息
            recommend_count=settings.AI_DEFAULT_RECOMMEND_COUNT,  # 推荐数量
            diagnose_name=self._infer_diagnose_name(cdss_message),
        )

    def _infer_diagnose_name(self, cdss_message: CDSSMessage) -> str:
        """从已知字段中尽力推导 diagnose_name。若无明确诊断，使用主诉/病史摘要做一个简要疑似诊断。"""
        # 可按实际规则调整，这里优先使用病史摘要中的第一句话或主诉简化
        text = cdss_message.itemData.abstractHistory or cdss_message.itemData.clinicInfo
        if not text:
            return ""
        # 取前25个字符作为简要描述
        return str(text).strip().replace("\n", " ")[:25]
    
    async def _call_external_ai_service(self, ai_request: PatientInfoRequest) -> List[AiRecommendationResult]:
        """调用外部AI服务（处理流式响应）"""
        
        url = f"{self.base_url}{self.endpoint}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # 发送请求，接收流式响应
                async with client.stream(
                    "POST",
                    url,
                    json=ai_request.dict(),
                    headers={"Accept": "text/event-stream"}
                ) as response:
                    response.raise_for_status()
                    
                    # 解析流式响应
                    recommendations = await self._parse_stream_response(response)
                    
                    return recommendations

            except httpx.TimeoutException:
                logger.bind(name="app.services.ai_service").error(
                    f"❌ AI服务调用超时: url={url}"
                )
                raise Exception("AI服务调用超时")
            except httpx.HTTPStatusError as e:
                logger.bind(name="app.services.ai_service").error(
                    f"❌ AI服务HTTP错误: status={e.response.status_code}, url={url}"
                )
                raise Exception(f"AI服务HTTP错误: {e.response.status_code}")
            except Exception as e:
                logger.bind(name="app.services.ai_service").error(f"❌ AI服务调用异常: {e}")
                raise
    
    async def _parse_stream_response(self, response) -> List[AiRecommendationResult]:
        """解析流式响应数据（更鲁棒，兼容多种SSE分片与结束标记）"""

        recommendations_dict: Dict[str, Dict[str, str]] = {}

        try:
            async for line in response.aiter_lines():
                if not line:
                    continue
                data_line = line.lstrip()
                if not data_line.startswith("data:"):
                    continue
                data_str = data_line[5:].strip()
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # 结束信号：兼容 {"finish": 1/true} 以及无 code 的结束包
                if isinstance(data, dict) and data.get("finish") in (1, True, "true", "True"):
                    break

                # 常规数据包：需要有 code==0 且 data 为对象
                if isinstance(data, dict) and data.get("code") == 0 and isinstance(data.get("data"), dict):
                    item_data = data["data"]
                    check_item_name = item_data.get("check_item_name", "")
                    reason = item_data.get("reason", "")
                    cautions = item_data.get("cautions", "")

                    if not check_item_name:
                        continue

                    if check_item_name not in recommendations_dict:
                        recommendations_dict[check_item_name] = {"reason": "", "cautions": ""}

                    # 累积拼接（理由与注意事项均为分片累加）
                    recommendations_dict[check_item_name]["reason"] += reason
                    recommendations_dict[check_item_name]["cautions"] += cautions

            # 转换为结果列表
            recommendations: List[AiRecommendationResult] = []
            for i, (name, agg) in enumerate(recommendations_dict.items(), 1):
                recommendations.append(
                    AiRecommendationResult(
                        check_item_name=name,
                        reason=agg["reason"].strip(),
                        cautions=agg["cautions"].strip(),
                        sequence=i,
                    )
                )

            return recommendations

        except Exception as e:
            logger.bind(name="app.services.ai_service").error(f"❌ 解析流式响应异常: {e}")
            raise Exception(f"解析AI服务响应失败: {e}")
    
    async def _save_ai_recommendation_log(
        self,
        request_id: str,
        client_id: str,
        cdss_message: CDSSMessage,
        his_push_log_id: Optional[int],
        ai_request_data: Optional[dict],
        recommendations: List[AiRecommendationResult],
        processing_time: float,
        status: str,
        error_message: Optional[str] = None
    ):
        """保存AI推荐日志"""
        
        try:
            ai_log = AiRecommendationLog(
                request_id=request_id,
                client_id=client_id,
                pat_no=cdss_message.patNo,
                adm_id=cdss_message.admId,
                user_code=cdss_message.userCode,
                dept_code=cdss_message.deptCode,
                message_id=getattr(cdss_message, 'message_id', None),
                his_push_log_id=his_push_log_id,
                ai_request_data=json.dumps(ai_request_data, ensure_ascii=False) if ai_request_data else None,
                ai_response_data=None,  # 暂不保存原始响应
                recommendations=json.dumps([rec.dict() for rec in recommendations], ensure_ascii=False),
                processing_time=processing_time,
                ai_service_url=f"{self.base_url}{self.endpoint}",
                session_id=cdss_message.admId,
                status=status,
                error_message=error_message
            )
            
            self.db.add(ai_log)
            await self.db.commit()
            await self.db.refresh(ai_log)
            
            logger.bind(name="app.services.ai_service").info(
                f"💾 AI推荐日志已保存: id={ai_log.id}, request_id={request_id}"
            )
            
        except Exception as e:
            await self.db.rollback()
            logger.bind(name="app.services.ai_service").error(f"❌ 保存AI推荐日志失败: {e}")
    
    async def get_cached_recommendation(self, patient_id: str, visit_id: str) -> Optional[List[AiRecommendationResult]]:
        """获取缓存的推荐结果（5分钟内的相同请求）"""
        try:
            from sqlalchemy import and_
            from datetime import datetime, timedelta
            
            # 查询5分钟内的成功推荐
            query = select(AiRecommendationLog).where(
                and_(
                    AiRecommendationLog.pat_no == patient_id,
                    AiRecommendationLog.adm_id == visit_id,
                    AiRecommendationLog.status == "success",
                    AiRecommendationLog.created_at >= datetime.now() - timedelta(minutes=5)
                )
            ).order_by(AiRecommendationLog.created_at.desc())
            
            result = await self.db.execute(query)
            latest_log = result.scalar_one_or_none()
            
            if latest_log and latest_log.recommendations:
                # 解析缓存的推荐结果
                recommendations_data = json.loads(latest_log.recommendations)
                recommendations = [AiRecommendationResult(**data) for data in recommendations_data]
                logger.bind(name="app.services.ai_service").info(
                    f"📋 使用缓存推荐: patient_id={patient_id}, visit_id={visit_id}"
                )
                return recommendations

            return None
            
        except Exception as e:
            logger.bind(name="app.services.ai_service").error(f"❌ 获取缓存推荐失败: {e}")
            return None

    async def _save_service_call(
        self,
        request_id: str,
        client_id: str,
        status: str,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """保存服务调用明细（用于统计）"""
        try:
            call = ServiceCall(
                request_id=request_id,
                client_id=client_id,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            self.db.add(call)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.bind(name="app.services.ai_service").error(f"❌ 保存服务调用明细失败: {e}")

    async def _ensure_ai_session(self, patient_id: str, visit_id: str | None, doctor_id: str | None) -> str:
        """确保存在会话，返回会话ID。session_key = patNo#YYYYMMDD"""
        from datetime import datetime
        session_key = f"{patient_id}#{datetime.now().strftime('%Y%m%d')}"
        try:
            from sqlalchemy import select
            existing = (
                await self.db.execute(
                    select(AiSession).where(AiSession.session_key == session_key)
                )
            ).scalar_one_or_none()
            if existing:
                return existing.id  # type: ignore
            row = AiSession(
                session_key=session_key,
                patient_id=patient_id,
                visit_id=visit_id,
                doctor_id=doctor_id,
            )
            self.db.add(row)
            await self.db.commit()
            await self.db.refresh(row)
            return row.id  # type: ignore
        except Exception as e:
            await self.db.rollback()
            logger.bind(name="app.services.ai_service").error(f"❌ 确保会话失败: {e}")
            raise

    async def _append_ai_session_record(self, session_id: str, request_id: str, summary: str | None) -> None:
        """追加会话明细记录"""
        try:
            rec = AiSessionRecord(session_id=session_id, request_id=request_id, summary=summary)
            self.db.add(rec)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.bind(name="app.services.ai_service").error(f"❌ 追加会话记录失败: {e}")