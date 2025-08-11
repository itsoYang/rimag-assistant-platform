"""
HIS相关业务服务
处理HIS推送数据的存储和关联客户端查找
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, Dict, Any
import json
from datetime import datetime
from loguru import logger

from app.models.database_models import HisPushLog, ClientConnection, SystemLog
from app.schemas.his_schemas import CDSSMessage


class HisService:
    """HIS相关业务服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_client_by_user_info(self, user_ip: str, user_code: str) -> Optional[str]:
        """
        根据用户IP和用户代码查找关联的客户端ID
        优先级1: userIP + userCode 精确匹配
        """
        try:
            # 查询在线的客户端连接
            query = select(ClientConnection).where(
                and_(
                    ClientConnection.ip_address == user_ip,
                    ClientConnection.doctor_id == user_code,
                    ClientConnection.connection_status == 'connected'
                )
            )
            
            result = await self.db.execute(query)
            client_conn = result.scalar_one_or_none()
            
            if client_conn:
                logger.info(f"🎯 找到精确匹配客户端: client_id={client_conn.client_id}")
                return client_conn.client_id
            
            logger.warning(f"⚠️ 未找到匹配客户端: userIP={user_ip}, userCode={user_code}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找客户端异常: {e}")
            return None
    
    async def save_his_push_log(
        self, 
        message_id: str, 
        cdss_message: CDSSMessage, 
        client_id: Optional[str],
        headers: Dict[str, str]
    ) -> HisPushLog:
        """保存HIS推送记录"""
        try:
            # 解析消息时间
            msg_time = None
            try:
                msg_time = datetime.strptime(cdss_message.msgTime, "%Y-%m-%d %H:%M:%S")
            except:
                msg_time = datetime.now()
            
            # 创建HIS推送记录
            his_log = HisPushLog(
                message_id=message_id,
                system_id=cdss_message.systemId,
                scene_type=cdss_message.sceneType,
                state=cdss_message.state,
                pat_no=cdss_message.patNo,
                pat_name=cdss_message.patName,
                adm_id=cdss_message.admId,
                visit_type=cdss_message.visitType,
                dept_code=cdss_message.deptCode,
                dept_desc=cdss_message.deptDesc,
                hosp_code=cdss_message.hospCode,
                hosp_desc=cdss_message.hospDesc,
                user_ip=cdss_message.userIP,
                user_code=cdss_message.userCode,
                user_name=cdss_message.userName,
                msg_time=msg_time,
                remark=cdss_message.remark,
                item_data=json.dumps(cdss_message.itemData.dict(), ensure_ascii=False),
                client_id=client_id,
                push_status="success" if client_id else "client_not_found",
                error_message=None if client_id else "未找到关联客户端"
            )
            
            self.db.add(his_log)
            await self.db.commit()
            await self.db.refresh(his_log)
            
            logger.info(f"💾 HIS推送记录已保存: id={his_log.id}, message_id={message_id}")
            return his_log
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 保存HIS推送记录失败: {e}")
            raise
    
    async def update_push_status(self, log_id: int, status: str, error_message: str = None):
        """更新推送状态"""
        try:
            query = select(HisPushLog).where(HisPushLog.id == log_id)
            result = await self.db.execute(query)
            his_log = result.scalar_one_or_none()
            
            if his_log:
                his_log.push_status = status
                his_log.error_message = error_message
                await self.db.commit()
                
                logger.info(f"📝 推送状态已更新: log_id={log_id}, status={status}")
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 更新推送状态失败: {e}")
    
    async def log_system_error(
        self, 
        module: str, 
        operation: str, 
        message: str, 
        details: Dict[str, Any] = None,
        client_id: str = None,
        request_id: str = None
    ):
        """记录系统错误日志"""
        try:
            system_log = SystemLog(
                log_level="ERROR",
                module=module,
                operation=operation,
                client_id=client_id,
                request_id=request_id,
                message=message,
                details=json.dumps(details, ensure_ascii=False) if details else None
            )
            
            self.db.add(system_log)
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"❌ 记录系统日志失败: {e}")
    
    async def get_his_push_logs(self, limit: int = 100, offset: int = 0):
        """获取HIS推送日志列表"""
        try:
            query = select(HisPushLog).order_by(HisPushLog.created_at.desc()).limit(limit).offset(offset)
            result = await self.db.execute(query)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"❌ 获取HIS推送日志失败: {e}")
            return []