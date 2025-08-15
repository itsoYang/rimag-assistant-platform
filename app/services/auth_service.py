"""权限验证服务
实现基础的RBAC权限控制，包括用户认证、权限检查和服务授权
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from loguru import logger
import jwt
from passlib.context import CryptContext

from app.models.database_models import (
    User, Role, Permission, UserRole, RolePermission,
    ServiceAuth, ClientInfo
)
from app.core.trace import TraceManager, SpanType, trace_function
from app.core.config import settings


class AuthService:
    """权限验证服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = getattr(settings, 'SECRET_KEY', 'your-secret-key-here')
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
    
    @trace_function("用户登录认证", SpanType.BUSINESS_LOGIC)
    async def authenticate_user(
        self,
        username: str,
        password: str,
        client_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """用户登录认证
        
        Args:
            username: 用户名
            password: 密码
            client_id: 客户端ID
            
        Returns:
            Optional[Dict[str, Any]]: 认证结果，包含用户信息和token
        """
        TraceManager.add_tag("username", username)
        TraceManager.add_tag("client_id", client_id or "unknown")
        
        try:
            # 查询用户信息
            query = (
                select(User)
                .options(selectinload(User.roles).selectinload(UserRole.role))
                .where(and_(User.username == username, User.is_active == True))
            )
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    username=username
                ).warning("⚠️ 用户不存在或已禁用")
                TraceManager.add_log("用户不存在或已禁用", "warning")
                return None
            
            # 验证密码
            if not self.verify_password(password, user.password_hash):
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    username=username,
                    user_id=user.user_id
                ).warning("⚠️ 密码验证失败")
                TraceManager.add_log("密码验证失败", "warning")
                return None
            
            # 更新最后登录时间
            user.last_login_time = datetime.now()
            if client_id:
                user.last_client_id = client_id
            
            # 生成访问令牌
            access_token = self._create_access_token(
                data={"sub": user.username, "user_id": user.user_id}
            )
            
            # 获取用户角色和权限
            roles = [ur.role.role_name for ur in user.roles if ur.role.is_active]
            permissions = await self._get_user_permissions(user.user_id)
            
            await self.db.commit()
            
            auth_result = {
                "user_id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "roles": roles,
                "permissions": list(permissions),
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60
            }
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                username=username,
                user_id=user.user_id
            ).info(f"✅ 用户登录成功, 角色: {roles}")
            
            TraceManager.add_tag("login_success", True)
            TraceManager.add_tag("user_roles", roles)
            
            return auth_result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 用户认证失败: {str(e)}")
            TraceManager.add_log(f"用户认证失败: {str(e)}", "error")
            raise
    
    @trace_function("验证访问令牌", SpanType.BUSINESS_LOGIC)
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证访问令牌
        
        Args:
            token: JWT访问令牌
            
        Returns:
            Optional[Dict[str, Any]]: 用户信息
        """
        try:
            # 解码JWT令牌
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            user_id: str = payload.get("user_id")
            
            if username is None or user_id is None:
                TraceManager.add_log("令牌payload无效", "warning")
                return None
            
            TraceManager.add_tag("username", username)
            TraceManager.add_tag("user_id", user_id)
            
            # 查询用户信息
            query = (
                select(User)
                .options(selectinload(User.roles).selectinload(UserRole.role))
                .where(and_(User.user_id == user_id, User.is_active == True))
            )
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                TraceManager.add_log("用户不存在或已禁用", "warning")
                return None
            
            # 获取用户权限
            permissions = await self._get_user_permissions(user.user_id)
            roles = [ur.role.role_name for ur in user.roles if ur.role.is_active]
            
            user_info = {
                "user_id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "roles": roles,
                "permissions": list(permissions)
            }
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                username=username,
                user_id=user_id
            ).debug("🔐 令牌验证成功")
            
            return user_info
            
        except jwt.ExpiredSignatureError:
            TraceManager.add_log("令牌已过期", "warning")
            return None
        except jwt.JWTError as e:
            TraceManager.add_log(f"令牌解码失败: {str(e)}", "warning")
            return None
        except Exception as e:
            logger.error(f"❌ 令牌验证失败: {str(e)}")
            TraceManager.add_log(f"令牌验证失败: {str(e)}", "error")
            raise
    
    @trace_function("检查用户权限", SpanType.BUSINESS_LOGIC)
    async def check_permission(
        self,
        user_id: str,
        permission_code: str,
        resource_id: Optional[str] = None
    ) -> bool:
        """检查用户权限
        
        Args:
            user_id: 用户ID
            permission_code: 权限代码
            resource_id: 资源ID（可选）
            
        Returns:
            bool: 是否有权限
        """
        TraceManager.add_tag("user_id", user_id)
        TraceManager.add_tag("permission_code", permission_code)
        
        try:
            # 获取用户权限
            permissions = await self._get_user_permissions(user_id)
            
            has_permission = permission_code in permissions
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                user_id=user_id,
                permission_code=permission_code
            ).debug(f"🔍 权限检查: {'✅' if has_permission else '❌'}")
            
            TraceManager.add_tag("has_permission", has_permission)
            
            return has_permission
            
        except Exception as e:
            logger.error(f"❌ 权限检查失败: {str(e)}")
            TraceManager.add_log(f"权限检查失败: {str(e)}", "error")
            return False
    
    @trace_function("服务授权验证", SpanType.BUSINESS_LOGIC)
    async def verify_service_auth(
        self,
        service_name: str,
        api_key: str,
        client_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """服务授权验证
        
        Args:
            service_name: 服务名称
            api_key: API密钥
            client_id: 客户端ID
            
        Returns:
            Optional[Dict[str, Any]]: 服务授权信息
        """
        TraceManager.add_tag("service_name", service_name)
        TraceManager.add_tag("client_id", client_id or "unknown")
        
        try:
            # 查询服务授权信息
            query = (
                select(ServiceAuth)
                .where(
                    and_(
                        ServiceAuth.service_name == service_name,
                        ServiceAuth.is_active == True
                    )
                )
            )
            result = await self.db.execute(query)
            service_auth = result.scalar_one_or_none()
            
            if not service_auth:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    service_name=service_name
                ).warning("⚠️ 服务授权不存在")
                return None
            
            # 验证API密钥
            if not self._verify_api_key(api_key, service_auth.api_key_hash):
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    service_name=service_name
                ).warning("⚠️ API密钥验证失败")
                return None
            
            # 检查过期时间
            if service_auth.expires_at and service_auth.expires_at < datetime.now():
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    service_name=service_name
                ).warning("⚠️ 服务授权已过期")
                return None
            
            # 更新最后使用时间
            service_auth.last_used_time = datetime.now()
            if client_id:
                service_auth.last_client_id = client_id
            
            await self.db.commit()
            
            auth_info = {
                "service_id": service_auth.service_id,
                "service_name": service_auth.service_name,
                "permissions": json.loads(service_auth.permissions) if service_auth.permissions else [],
                "rate_limit": service_auth.rate_limit,
                "metadata": json.loads(service_auth.metadata) if service_auth.metadata else {}
            }
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                service_name=service_name,
                service_id=service_auth.service_id
            ).info("✅ 服务授权验证成功")
            
            TraceManager.add_tag("service_auth_success", True)
            
            return auth_info
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 服务授权验证失败: {str(e)}")
            TraceManager.add_log(f"服务授权验证失败: {str(e)}", "error")
            raise
    
    @trace_function("客户端认证", SpanType.BUSINESS_LOGIC)
    async def authenticate_client(
        self,
        client_id: str,
        client_secret: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """客户端认证
        
        Args:
            client_id: 客户端ID
            client_secret: 客户端密钥（可选）
            
        Returns:
            Optional[Dict[str, Any]]: 客户端信息
        """
        TraceManager.add_tag("client_id", client_id)
        
        try:
            # 查询客户端信息
            query = (
                select(ClientInfo)
                .where(
                    and_(
                        ClientInfo.client_id == client_id,
                        ClientInfo.is_active == True
                    )
                )
            )
            result = await self.db.execute(query)
            client_info = result.scalar_one_or_none()
            
            if not client_info:
                logger.bind(
                    trace_id=TraceManager.get_current_trace_id(),
                    client_id=client_id
                ).warning("⚠️ 客户端不存在或已禁用")
                return None
            
            # 如果需要验证客户端密钥
            if client_secret and client_info.client_secret:
                if not self._verify_client_secret(client_secret, client_info.client_secret):
                    logger.bind(
                        trace_id=TraceManager.get_current_trace_id(),
                        client_id=client_id
                    ).warning("⚠️ 客户端密钥验证失败")
                    return None
            
            # 更新最后连接时间
            client_info.last_connect_time = datetime.now()
            await self.db.commit()
            
            client_data = {
                "client_id": client_info.client_id,
                "client_name": client_info.client_name,
                "client_type": client_info.client_type,
                "permissions": json.loads(client_info.permissions) if client_info.permissions else [],
                "metadata": json.loads(client_info.metadata) if client_info.metadata else {}
            }
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                client_id=client_id
            ).info("✅ 客户端认证成功")
            
            TraceManager.add_tag("client_auth_success", True)
            
            return client_data
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 客户端认证失败: {str(e)}")
            TraceManager.add_log(f"客户端认证失败: {str(e)}", "error")
            raise
    
    def hash_password(self, password: str) -> str:
        """密码哈希"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def _create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def _verify_api_key(self, api_key: str, api_key_hash: str) -> bool:
        """验证API密钥"""
        # 使用SHA256哈希验证
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return key_hash == api_key_hash
    
    def _verify_client_secret(self, client_secret: str, stored_secret: str) -> bool:
        """验证客户端密钥"""
        # 简单的字符串比较，实际应用中应该使用哈希
        return client_secret == stored_secret
    
    async def _get_user_permissions(self, user_id: str) -> Set[str]:
        """获取用户权限集合"""
        try:
            # 通过用户角色获取权限
            query = (
                select(Permission.permission_code)
                .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
                .join(Role, RolePermission.role_id == Role.role_id)
                .join(UserRole, Role.role_id == UserRole.role_id)
                .where(
                    and_(
                        UserRole.user_id == user_id,
                        Role.is_active == True,
                        Permission.is_active == True
                    )
                )
            )
            
            result = await self.db.execute(query)
            permissions = result.scalars().all()
            
            return set(permissions)
            
        except Exception as e:
            logger.error(f"❌ 获取用户权限失败: {str(e)}")
            return set()
    
    @trace_function("创建用户", SpanType.BUSINESS_LOGIC)
    async def create_user(
        self,
        username: str,
        password: str,
        email: str,
        display_name: str,
        roles: Optional[List[str]] = None
    ) -> Optional[str]:
        """创建用户
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            display_name: 显示名称
            roles: 角色列表
            
        Returns:
            Optional[str]: 用户ID
        """
        TraceManager.add_tag("username", username)
        TraceManager.add_tag("email", email)
        
        try:
            # 检查用户名是否已存在
            existing_query = select(User).where(User.username == username)
            existing_result = await self.db.execute(existing_query)
            if existing_result.scalar_one_or_none():
                logger.warning(f"⚠️ 用户名已存在: {username}")
                return None
            
            # 创建用户
            import uuid
            user_id = str(uuid.uuid4())
            
            user = User(
                user_id=user_id,
                username=username,
                password_hash=self.hash_password(password),
                email=email,
                display_name=display_name,
                is_active=True,
                created_time=datetime.now()
            )
            
            self.db.add(user)
            
            # 分配角色
            if roles:
                for role_name in roles:
                    role_query = select(Role).where(Role.role_name == role_name)
                    role_result = await self.db.execute(role_query)
                    role = role_result.scalar_one_or_none()
                    
                    if role:
                        user_role = UserRole(
                            user_id=user_id,
                            role_id=role.role_id,
                            assigned_time=datetime.now()
                        )
                        self.db.add(user_role)
            
            await self.db.commit()
            
            logger.bind(
                trace_id=TraceManager.get_current_trace_id(),
                username=username,
                user_id=user_id
            ).info(f"✅ 用户创建成功, 角色: {roles or []}")
            
            TraceManager.add_tag("user_created", True)
            
            return user_id
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ 创建用户失败: {str(e)}")
            TraceManager.add_log(f"创建用户失败: {str(e)}", "error")
            raise
    
    @trace_function("获取用户信息", SpanType.DATABASE)
    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[Dict[str, Any]]: 用户信息
        """
        TraceManager.add_tag("user_id", user_id)
        
        try:
            query = (
                select(User)
                .options(selectinload(User.roles).selectinload(UserRole.role))
                .where(User.user_id == user_id)
            )
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            roles = [ur.role.role_name for ur in user.roles if ur.role.is_active]
            permissions = await self._get_user_permissions(user_id)
            
            user_info = {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "is_active": user.is_active,
                "roles": roles,
                "permissions": list(permissions),
                "created_time": user.created_time.isoformat() if user.created_time else None,
                "last_login_time": user.last_login_time.isoformat() if user.last_login_time else None
            }
            
            return user_info
            
        except Exception as e:
            logger.error(f"❌ 获取用户信息失败: {str(e)}")
            TraceManager.add_log(f"获取用户信息失败: {str(e)}", "error")
            raise