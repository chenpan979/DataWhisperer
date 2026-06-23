from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ModelProviderPayload(BaseModel):
    """前端系统设置页展示的模型供应商信息。

    接口不会返回真实 API Key，只返回是否已保存和脱敏后的 key_mask。
    """

    id: int
    name: str
    provider_type: str
    base_url: str
    status: str
    api_key_saved: bool
    api_key_mask: str | None = None
    last_checked_at: datetime | None = None


class ModelProfilePayload(BaseModel):
    """模型调用 Profile。"""

    id: int
    name: str
    chat_model: str
    embedding_model: str | None = None
    temperature: float
    max_tokens: int
    is_default: bool
    status: str


class AgentModelBindingPayload(BaseModel):
    """Agent 与模型 Profile 的绑定信息。"""

    id: int
    agent_key: str
    agent_label: str
    capability: str
    capability_label: str
    model_profile_id: int
    model_profile_name: str
    enabled: bool
    params: dict[str, Any] = Field(default_factory=dict)


class ModelSettingsPayload(BaseModel):
    """系统设置页模型配置的整体响应。"""

    provider: ModelProviderPayload
    profile: ModelProfilePayload
    agent_bindings: list[AgentModelBindingPayload]


class ModelSettingsUpdateRequest(BaseModel):
    """保存默认模型配置。

    api_key 为空或为 ****** 时表示沿用后端已保存的密钥，不做覆盖。
    """

    provider_name: str = Field(min_length=1, max_length=128)
    provider_type: str = Field(default="dashscope", min_length=2, max_length=32)
    base_url: str = Field(min_length=8, max_length=512)
    api_key: str | None = Field(default=None, max_length=1024)
    profile_name: str = Field(default="默认模型配置", min_length=1, max_length=128)
    chat_model: str = Field(min_length=1, max_length=128)
    embedding_model: str | None = Field(default=None, max_length=128)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=128, le=128000)


class ModelConnectionTestResponse(BaseModel):
    """模型配置检测结果。"""

    ok: bool
    message: str
    status: str
    latency_ms: int
    checked_at: datetime


class AgentModelBindingUpdateItem(BaseModel):
    """更新某个 Agent 能力的模型绑定。"""

    agent_key: str = Field(min_length=1, max_length=64)
    capability: str = Field(min_length=1, max_length=64)
    model_profile_id: int
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class AgentModelBindingUpdateRequest(BaseModel):
    """批量更新 Agent 模型绑定。"""

    bindings: list[AgentModelBindingUpdateItem]
