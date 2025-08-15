"""
权限校验服务（简化版）
规则：
- 若客户端未绑定任何角色，则放行（默认允许）
- 若已绑定角色，则需命中至少一条 allow=True 的 ACL 规则，否则拒绝
  （服务维度暂不细分，后续可通过 service_id/endpoint_id 精确控制）
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import ClientRoleBinding, RoleServiceAcl


async def is_client_allowed(db: AsyncSession, client_id: str) -> bool:
    """判断客户端是否允许发起受控调用（简化：只要任一角色存在 allow 规则即放行）"""
    # 查询客户端绑定的角色
    bindings = (
        await db.execute(
            select(ClientRoleBinding.role_id).where(ClientRoleBinding.client_id == client_id)
        )
    ).scalars().all()
    if not bindings:
        return True

    # 存在任意 allow 规则则放行
    allow_rule = (
        await db.execute(
            select(RoleServiceAcl).where(RoleServiceAcl.role_id.in_(bindings), RoleServiceAcl.allow == True)  # noqa: E712
        )
    ).scalars().first()
    return bool(allow_rule)


