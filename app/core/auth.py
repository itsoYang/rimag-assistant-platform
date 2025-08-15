"""
认证和授权模块
提供JWT令牌验证、用户认证等功能
"""

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from loguru import logger
from app.core.config import settings
from app.services.auth_service import AuthService


# HTTP Bearer认证
security = HTTPBearer(auto_error=False)

# 认证服务实例
auth_service = AuthService()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    获取当前用户信息
    从JWT令牌中解析用户信息
    """
    if not credentials:
        return None
    
    try:
        # 验证JWT令牌
        user_info = await auth_service.verify_token(credentials.credentials)
        return user_info
    except Exception as e:
        logger.warning(f"令牌验证失败: {e}")
        return None


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    要求用户认证
    如果未认证则抛出401错误
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # 验证JWT令牌
        user_info = await auth_service.verify_token(credentials.credentials)
        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"认证验证失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证验证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def check_permission(
    user: Dict[str, Any],
    required_permission: str
) -> bool:
    """
    检查用户权限
    """
    try:
        return await auth_service.check_permission(
            user.get("user_id"),
            required_permission
        )
    except Exception as e:
        logger.error(f"权限检查失败: {e}")
        return False


def require_permission(permission: str):
    """
    权限装饰器
    要求用户具有指定权限
    """
    async def permission_checker(
        user: Dict[str, Any] = Depends(require_auth)
    ) -> Dict[str, Any]:
        has_permission = await check_permission(user, permission)
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission}"
            )
        return user
    
    return permission_checker


async def verify_service_auth(
    service_id: str,
    api_key: str
) -> bool:
    """
    验证服务认证
    用于服务间调用的认证
    """
    try:
        return await auth_service.verify_service_auth(service_id, api_key)
    except Exception as e:
        logger.error(f"服务认证验证失败: {e}")
        return False


async def authenticate_client(
    client_id: str,
    client_secret: Optional[str] = None
) -> bool:
    """
    客户端认证
    用于WebSocket连接等场景
    """
    try:
        return await auth_service.authenticate_client(client_id, client_secret)
    except Exception as e:
        logger.error(f"客户端认证失败: {e}")
        return False