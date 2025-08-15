"""
管理端相关 Pydantic 模型
"""

from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field


class ServiceCreate(BaseModel):
    name: str
    type: str = Field(pattern=r"^(HIS_SERVICE|MODEL_SERVICE)$")
    base_path: str
    protocol: str = Field(pattern=r"^(HTTP|WEBSOCKET)$")
    enabled: Optional[bool] = True
    description: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern=r"^(HIS_SERVICE|MODEL_SERVICE)$")
    base_path: Optional[str] = None
    protocol: Optional[str] = Field(default=None, pattern=r"^(HTTP|WEBSOCKET)$")
    enabled: Optional[bool] = None
    description: Optional[str] = None


class ServiceOut(BaseModel):
    id: str
    name: str
    type: str
    base_path: str
    protocol: str
    enabled: bool
    description: Optional[str] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None


class ServiceEndpointCreate(BaseModel):
    service_id: str
    name: str
    path: str
    method: str = Field(default="POST")
    target_url: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=5, ge=1, le=120)
    enabled: Optional[bool] = True


class ServiceEndpointUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None
    target_url: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    enabled: Optional[bool] = None


class ServiceEndpointOut(BaseModel):
    id: str
    service_id: str
    name: str
    path: str
    method: str
    target_url: Optional[str] = None
    timeout_seconds: int
    enabled: bool
    create_time: Optional[str] = None
    update_time: Optional[str] = None


class TestConnectionResult(BaseModel):
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


# ===== 权限模型 =====


class RoleCreate(BaseModel):
    role_name: str
    type: Optional[str] = Field(default='DEPT', pattern=r"^(DEPT|CUSTOM)$")
    description: Optional[str] = None
    enabled: Optional[bool] = True


class RoleUpdate(BaseModel):
    role_name: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern=r"^(DEPT|CUSTOM)$")
    description: Optional[str] = None
    enabled: Optional[bool] = None


class RoleOut(BaseModel):
    role_id: str
    role_name: str
    type: Optional[str] = None
    description: Optional[str] = None
    enabled: bool


class RoleAclCreate(BaseModel):
    role_id: str
    service_id: str


class RoleAclOut(BaseModel):
    id: str
    role_id: str
    service_id: str


class ClientRoleBindCreate(BaseModel):
    client_id: str
    role_id: str


class ClientRoleBindOut(BaseModel):
    id: str
    client_id: str
    role_id: str


