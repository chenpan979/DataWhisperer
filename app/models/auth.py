from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    """登录请求。"""

    tenant_key: str = Field(min_length=2, max_length=64, description="租户/工作空间标识。")
    account: str = Field(min_length=1, max_length=128, description="账号，可以是邮箱或显示名。")
    password: str = Field(min_length=1, max_length=128, description="登录密码。")


class AuthRegisterRequest(BaseModel):
    """注册并创建租户空间请求。"""

    tenant_name: str = Field(min_length=2, max_length=128, description="公司或团队名称。")
    tenant_key: str = Field(min_length=3, max_length=64, description="租户唯一标识。")
    display_name: str = Field(min_length=1, max_length=64, description="管理员显示名称。")
    email: str = Field(min_length=5, max_length=128, description="管理员邮箱。")
    password: str = Field(min_length=8, max_length=128, description="管理员密码。")


class PasswordResetRequest(BaseModel):
    """找回密码请求。

    当前版本只返回前端演示状态，后续可以接邮件验证码或管理员重置流程。
    """

    tenant_key: str = Field(min_length=2, max_length=64)
    email: str = Field(min_length=5, max_length=128)


class AuthUser(BaseModel):
    """当前登录用户。"""

    id: int
    email: str
    display_name: str
    role: str
    avatar_url: str | None = None


class AuthTenant(BaseModel):
    """当前租户。"""

    id: int
    tenant_key: str
    name: str
    plan: str


class AuthWorkspace(BaseModel):
    """当前工作空间。"""

    id: int
    workspace_key: str
    name: str


class AuthSessionResponse(BaseModel):
    """登录/注册成功后的会话响应。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUser
    tenant: AuthTenant
    workspace: AuthWorkspace


class AuthMeResponse(BaseModel):
    """当前用户响应。"""

    user: AuthUser
    tenant: AuthTenant
    workspace: AuthWorkspace


class PasswordResetResponse(BaseModel):
    """找回密码响应。"""

    accepted: bool
    message: str
