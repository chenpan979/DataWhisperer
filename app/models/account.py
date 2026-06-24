from __future__ import annotations

from pydantic import BaseModel, Field


class AccountPreferencePayload(BaseModel):
    """系统设置页账号偏好的后端响应。"""

    user_id: int
    email: str
    display_name: str
    role: str
    role_title: str
    avatar_url: str | None = None
    language: str
    default_view: str


class AccountPreferenceUpdateRequest(BaseModel):
    """保存账号偏好。

    display_name 和 avatar_url 属于账号基础资料；role_title、language、default_view
    属于当前租户下的工作台偏好。
    """

    display_name: str = Field(min_length=1, max_length=64)
    role_title: str = Field(min_length=1, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=2_000_000)
    language: str = Field(default="zh-CN", min_length=2, max_length=16)
    default_view: str = Field(default="analysisView", min_length=1, max_length=64)


class PasswordChangeRequest(BaseModel):
    """修改当前登录账号密码。"""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeResponse(BaseModel):
    """密码修改结果。"""

    ok: bool
    message: str