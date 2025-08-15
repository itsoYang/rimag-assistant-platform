"""会话管理服务
实现基于患者+日期的会话管理，支持AI推荐会话的创建、查询和状态管理
"""

import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload
from loguru import logger

from app.models.database_models import AiSession, AiSessionRecord, Patient
from app.core.trace import TraceManager, SpanType, trace_function


class SessionService:
    """会话管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @trace_function("创建或获取AI会话", SpanType.BUSINESS_LOGIC)
    async def ensure_ai_session(
        self,
        patient_id: str,
        session_date: Optional[date] = None,
        client_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> AiSession:
        """确保AI会话存在，如果不存在则创建
        
        Args:
            patient_id: 患者ID
            session_date: 会话日期，默认为今天
            client_id: 客户端ID
            trace_id: 调用链ID
            
        Returns:
            AiSession: AI会话对象
        """
        if not session_date:
            session_date = date.today()
        
        TraceManager.add_tag("patient_id", patient_id)
        TraceManager.add_tag("session_date", session_date.isoformat())
        
        try:
            # 查询是否已存在会话
            query = select(AiSession).where(
                and_(
                    AiSession.patient_id == patient_id,
                    AiSession.session_date == session_date
                )
            )
            result = await self.db.execute(query)
            existing_session = result.scalar_one_or_none()
            
            if existing_session:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    patient_id=patient_id,
                    session_id=existing_session.session_id
                ).info("📋 找到已存在的AI会话")
                
                # 更新最后活跃时间和客户端ID
                existing_session.last_active_time = datetime.now()
                if client_id:
                    existing_session.client_id = client_id
                if trace_id:
                    existing_session.trace_id = trace_id
                
                await self.db.commit()
                return existing_session
            
            # 创建新会话
            session_id = self._generate_session_id(patient_id, session_date)
            
            new_session = AiSession(
                session_id=session_id,
                patient_id=patient_id,
                session_date=session_date,
                client_id=client_id,
                trace_id=trace_id,
                created_time=datetime.now(),
                last_active_time=datetime.now(),
                status="active",
                metadata={}
            )
            
            self.db.add(new_session)
            await self.db.commit()
            await self.db.refresh(new_session)
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                patient_id=patient_id,
                session_id=session_id
            ).info("✨ 创建新的AI会话")
            
            TraceManager.add_tag("session_id", session_id)
            TraceManager.add_tag("session_created", True)
            
            return new_session
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 创建或获取AI会话失败: {str(e)}")
            TraceManager.add_log(f"会话管理失败: {str(e)}", "error")
            raise
    
    @trace_function("添加会话记录", SpanType.BUSINESS_LOGIC)
    async def add_session_record(
        self,
        session_id: str,
        record_type: str,
        content: Dict[str, Any],
        ai_recommendation_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> AiSessionRecord:
        """添加会话记录
        
        Args:
            session_id: 会话ID
            record_type: 记录类型 (his_push, ai_request, ai_response, user_feedback)
            content: 记录内容
            ai_recommendation_id: AI推荐ID
            trace_id: 调用链ID
            
        Returns:
            AiSessionRecord: 会话记录对象
        """
        TraceManager.add_tag("session_id", session_id)
        TraceManager.add_tag("record_type", record_type)
        
        try:
            record = AiSessionRecord(
                session_id=session_id,
                record_type=record_type,
                content=content,
                ai_recommendation_id=ai_recommendation_id,
                trace_id=trace_id,
                created_time=datetime.now()
            )
            
            self.db.add(record)
            
            # 更新会话的最后活跃时间
            await self._update_session_active_time(session_id)
            
            await self.db.commit()
            await self.db.refresh(record)
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                session_id=session_id,
                record_id=record.record_id
            ).info(f"📝 添加会话记录: {record_type}")
            
            return record
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 添加会话记录失败: {str(e)}")
            TraceManager.add_log(f"添加会话记录失败: {str(e)}", "error")
            raise
    
    @trace_function("获取会话信息", SpanType.DATABASE)
    async def get_session(
        self,
        session_id: str,
        include_records: bool = False
    ) -> Optional[AiSession]:
        """获取会话信息
        
        Args:
            session_id: 会话ID
            include_records: 是否包含会话记录
            
        Returns:
            Optional[AiSession]: 会话对象
        """
        TraceManager.add_tag("session_id", session_id)
        
        try:
            query = select(AiSession).where(AiSession.session_id == session_id)
            
            if include_records:
                query = query.options(selectinload(AiSession.records))
            
            result = await self.db.execute(query)
            session = result.scalar_one_or_none()
            
            if session:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    session_id=session_id
                ).info("🔍 获取会话信息成功")
            else:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    session_id=session_id
                ).warning("⚠️ 会话不存在")
            
            return session
            
        except Exception as e:
            logger.error(f"❌ 获取会话信息失败: {str(e)}")
            TraceManager.add_log(f"获取会话信息失败: {str(e)}", "error")
            raise
    
    @trace_function("获取患者会话列表", SpanType.DATABASE)
    async def get_patient_sessions(
        self,
        patient_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[AiSession]:
        """获取患者的会话列表
        
        Args:
            patient_id: 患者ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[AiSession]: 会话列表
        """
        TraceManager.add_tag("patient_id", patient_id)
        
        try:
            query = (
                select(AiSession)
                .where(AiSession.patient_id == patient_id)
                .order_by(desc(AiSession.session_date), desc(AiSession.created_time))
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(query)
            sessions = result.scalars().all()
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                patient_id=patient_id
            ).info(f"📋 获取患者会话列表: {len(sessions)}个会话")
            
            return list(sessions)
            
        except Exception as e:
            logger.error(f"❌ 获取患者会话列表失败: {str(e)}")
            TraceManager.add_log(f"获取患者会话列表失败: {str(e)}", "error")
            raise
    
    @trace_function("获取会话记录", SpanType.DATABASE)
    async def get_session_records(
        self,
        session_id: str,
        record_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[AiSessionRecord]:
        """获取会话记录
        
        Args:
            session_id: 会话ID
            record_type: 记录类型过滤
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[AiSessionRecord]: 会话记录列表
        """
        TraceManager.add_tag("session_id", session_id)
        
        try:
            query = (
                select(AiSessionRecord)
                .where(AiSessionRecord.session_id == session_id)
            )
            
            if record_type:
                query = query.where(AiSessionRecord.record_type == record_type)
                TraceManager.add_tag("record_type", record_type)
            
            query = (
                query
                .order_by(desc(AiSessionRecord.created_time))
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(query)
            records = result.scalars().all()
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                session_id=session_id
            ).info(f"📝 获取会话记录: {len(records)}条记录")
            
            return list(records)
            
        except Exception as e:
            logger.error(f"❌ 获取会话记录失败: {str(e)}")
            TraceManager.add_log(f"获取会话记录失败: {str(e)}", "error")
            raise
    
    @trace_function("更新会话状态", SpanType.DATABASE)
    async def update_session_status(
        self,
        session_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新会话状态
        
        Args:
            session_id: 会话ID
            status: 新状态 (active, inactive, closed)
            metadata: 元数据更新
            
        Returns:
            bool: 更新是否成功
        """
        TraceManager.add_tag("session_id", session_id)
        TraceManager.add_tag("new_status", status)
        
        try:
            query = select(AiSession).where(AiSession.session_id == session_id)
            result = await self.db.execute(query)
            session = result.scalar_one_or_none()
            
            if not session:
                logger.warning(f"⚠️ 会话不存在: {session_id}")
                return False
            
            session.status = status
            session.last_active_time = datetime.now()
            
            if metadata:
                # 合并元数据
                current_metadata = session.metadata or {}
                current_metadata.update(metadata)
                session.metadata = current_metadata
            
            await self.db.commit()
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                session_id=session_id
            ).info(f"✅ 更新会话状态: {status}")
            
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 更新会话状态失败: {str(e)}")
            TraceManager.add_log(f"更新会话状态失败: {str(e)}", "error")
            raise
    
    @trace_function("获取活跃会话统计", SpanType.DATABASE)
    async def get_active_sessions_stats(self) -> Dict[str, Any]:
        """获取活跃会话统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            # 今日活跃会话数
            today = date.today()
            today_query = (
                select(func.count(AiSession.session_id))
                .where(
                    and_(
                        AiSession.session_date == today,
                        AiSession.status == "active"
                    )
                )
            )
            today_result = await self.db.execute(today_query)
            today_active = today_result.scalar() or 0
            
            # 总活跃会话数
            total_query = (
                select(func.count(AiSession.session_id))
                .where(AiSession.status == "active")
            )
            total_result = await self.db.execute(total_query)
            total_active = total_result.scalar() or 0
            
            # 最近7天会话数
            from datetime import timedelta
            week_ago = today - timedelta(days=7)
            week_query = (
                select(func.count(AiSession.session_id))
                .where(AiSession.session_date >= week_ago)
            )
            week_result = await self.db.execute(week_query)
            week_sessions = week_result.scalar() or 0
            
            stats = {
                "today_active_sessions": today_active,
                "total_active_sessions": total_active,
                "week_sessions": week_sessions,
                "stats_time": datetime.now().isoformat()
            }
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id()
            ).info(f"📊 获取活跃会话统计: 今日{today_active}, 总计{total_active}")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取活跃会话统计失败: {str(e)}")
            TraceManager.add_log(f"获取活跃会话统计失败: {str(e)}", "error")
            raise
    
    async def _update_session_active_time(self, session_id: str):
        """更新会话最后活跃时间"""
        try:
            query = select(AiSession).where(AiSession.session_id == session_id)
            result = await self.db.execute(query)
            session = result.scalar_one_or_none()
            
            if session:
                session.last_active_time = datetime.now()
                # 注意：这里不提交，由调用方统一提交
                
        except Exception as e:
            logger.error(f"❌ 更新会话活跃时间失败: {str(e)}")
    
    def _generate_session_id(self, patient_id: str, session_date: date) -> str:
        """生成会话ID
        
        格式: session_{patient_id}_{date}_{timestamp}
        """
        import time
        timestamp = int(time.time() * 1000)
        date_str = session_date.strftime("%Y%m%d")
        return f"session_{patient_id}_{date_str}_{timestamp}"
    
    @trace_function("清理过期会话", SpanType.BUSINESS_LOGIC)
    async def cleanup_expired_sessions(self, days_threshold: int = 30) -> int:
        """清理过期会话
        
        Args:
            days_threshold: 过期天数阈值
            
        Returns:
            int: 清理的会话数量
        """
        from datetime import timedelta
        
        try:
            cutoff_date = date.today() - timedelta(days=days_threshold)
            
            # 查询过期会话
            query = (
                select(AiSession)
                .where(
                    and_(
                        AiSession.session_date < cutoff_date,
                        AiSession.status != "closed"
                    )
                )
            )
            
            result = await self.db.execute(query)
            expired_sessions = result.scalars().all()
            
            # 更新状态为已关闭
            count = 0
            for session in expired_sessions:
                session.status = "closed"
                session.last_active_time = datetime.now()
                count += 1
            
            await self.db.commit()
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id()
            ).info(f"🧹 清理过期会话: {count}个会话")
            
            TraceManager.add_tag("cleaned_sessions", count)
            
            return count
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 清理过期会话失败: {str(e)}")
            TraceManager.add_log(f"清理过期会话失败: {str(e)}", "error")
            raise