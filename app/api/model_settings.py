from __future__ import annotations

import base64
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.config import get_settings
from app.core.product_database import get_product_session
from app.db.product_models import ModelCredential, ModelProfile, ModelProvider
from app.models.model_settings import (
    AgentModelBindingPayload,
    AgentModelBindingUpdateRequest,
    ModelConnectionTestResponse,
    ModelProfilePayload,
    ModelProviderPayload,
    ModelSettingsPayload,
    ModelSettingsUpdateRequest,
)
from app.repositories.product import ModelSettingsRepository

router = APIRouter(prefix="/model-settings", tags=["model_settings"])

SECRET_PLACEHOLDERS = {"", "******", "********", "sk-****", "已保存"}

DEFAULT_AGENT_BINDINGS = (
    {
        "agent_key": "sql_agent",
        "agent_label": "SQL 生成 Agent",
        "capability": "sql_generation",
        "capability_label": "自然语言转 SQL",
    },
    {
        "agent_key": "insight_agent",
        "agent_label": "分析总结 Agent",
        "capability": "insight_summary",
        "capability_label": "业务结论生成",
    },
    {
        "agent_key": "chart_agent",
        "agent_label": "图表推荐 Agent",
        "capability": "chart_recommendation",
        "capability_label": "可视化推荐",
    },
    {
        "agent_key": "rag_agent",
        "agent_label": "RAG 检索 Agent",
        "capability": "embedding",
        "capability_label": "知识库向量化",
    },
)


@router.get("/default", response_model=ModelSettingsPayload)
def get_default_model_settings(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> ModelSettingsPayload:
    """读取当前工作空间默认模型配置。

    系统设置页会用这个接口回填模型供应商、模型名和 Agent 绑定关系。
    """

    provider, profile = _ensure_default_model_settings(session=session, auth_context=auth_context)
    return _build_model_settings_payload(session=session, provider=provider, profile=profile)


@router.patch("/default", response_model=ModelSettingsPayload)
def update_default_model_settings(
    payload: ModelSettingsUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> ModelSettingsPayload:
    """保存当前工作空间默认模型配置。

    API Key 为空或为占位符时，不覆盖后端已保存的密钥。
    """

    provider, profile = _ensure_default_model_settings(session=session, auth_context=auth_context)
    repository = ModelSettingsRepository(session)
    repository.update_provider(
        provider,
        name=payload.provider_name.strip(),
        provider_type=_normalize_provider_type(payload.provider_type),
        base_url=payload.base_url.strip(),
        status="configured",
    )
    repository.update_profile(
        profile,
        name=payload.profile_name.strip(),
        chat_model=payload.chat_model.strip(),
        embedding_model=(payload.embedding_model or "").strip() or None,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        is_default=True,
        status="active",
    )
    if not _is_secret_placeholder(payload.api_key):
        repository.save_credential(
            provider_id=provider.id,
            encrypted_api_key=_encode_demo_secret(payload.api_key or ""),
            key_mask=_mask_secret(payload.api_key or ""),
        )
    _ensure_default_bindings(
        repository=repository,
        auth_context=auth_context,
        profile=profile,
    )
    session.commit()
    return _build_model_settings_payload(session=session, provider=provider, profile=profile)


@router.post("/default/test", response_model=ModelConnectionTestResponse)
def test_default_model_settings(
    payload: ModelSettingsUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> ModelConnectionTestResponse:
    """检测模型配置是否具备可用的基础信息。

    当前版本先做服务端结构校验和密钥存在性检查，避免测试环境依赖真实外网模型。
    后续如果接入企业模型网关，可以在这里发起轻量 Chat/Embedding ping。
    """

    provider, _profile = _ensure_default_model_settings(session=session, auth_context=auth_context)
    started_at = time.perf_counter()
    checked_at = datetime.now()
    ok = True
    message = "模型配置完整，已为后续 Agent 绑定预留。"
    status_value = "configured"

    if not payload.base_url.strip().startswith(("http://", "https://")):
        ok = False
        message = "Base URL 必须以 http:// 或 https:// 开头。"
        status_value = "failed"
    elif not payload.chat_model.strip():
        ok = False
        message = "Chat 模型不能为空。"
        status_value = "failed"
    elif _is_secret_placeholder(payload.api_key) and provider.credential is None:
        ok = False
        message = "请先填写并保存模型 API Key。"
        status_value = "failed"

    ModelSettingsRepository(session).update_provider(
        provider,
        status=status_value,
        last_checked_at=checked_at,
    )
    session.commit()
    return ModelConnectionTestResponse(
        ok=ok,
        message=message,
        status=status_value,
        latency_ms=max(1, round((time.perf_counter() - started_at) * 1000)),
        checked_at=checked_at,
    )


@router.get("/agent-bindings", response_model=list[AgentModelBindingPayload])
def list_agent_model_bindings(
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> list[AgentModelBindingPayload]:
    """读取当前工作空间的 Agent 模型绑定。"""

    provider, profile = _ensure_default_model_settings(session=session, auth_context=auth_context)
    return _build_model_settings_payload(session=session, provider=provider, profile=profile).agent_bindings


@router.patch("/agent-bindings", response_model=list[AgentModelBindingPayload])
def update_agent_model_bindings(
    payload: AgentModelBindingUpdateRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> list[AgentModelBindingPayload]:
    """批量更新 Agent 模型绑定。"""

    repository = ModelSettingsRepository(session)
    provider, default_profile = _ensure_default_model_settings(session=session, auth_context=auth_context)
    profile_ids = {profile.id for profile in provider.profiles}
    for item in payload.bindings:
        if item.model_profile_id not in profile_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="模型 Profile 不属于当前工作空间。")
        repository.upsert_binding(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            agent_key=item.agent_key.strip(),
            capability=item.capability.strip(),
            model_profile_id=item.model_profile_id,
            enabled=item.enabled,
            params_json=item.params,
        )
    _ensure_default_bindings(repository=repository, auth_context=auth_context, profile=default_profile)
    session.commit()
    return _build_model_settings_payload(session=session, provider=provider, profile=default_profile).agent_bindings


def _ensure_default_model_settings(
    *,
    session: Session,
    auth_context: AuthContext,
) -> tuple[ModelProvider, ModelProfile]:
    """确保当前工作空间有默认模型供应商、Profile 和 Agent 绑定。"""

    repository = ModelSettingsRepository(session)
    provider = repository.get_default_provider(workspace_id=auth_context.workspace.id)
    settings = get_settings()
    if provider is None:
        provider = repository.create_provider(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            name="DashScope",
            provider_type="dashscope",
            base_url=settings.effective_llm_base_url,
            status="configured" if settings.effective_llm_api_key else "unknown",
            created_by=auth_context.user.id,
        )
        if settings.effective_llm_api_key:
            repository.save_credential(
                provider_id=provider.id,
                encrypted_api_key=_encode_demo_secret(settings.effective_llm_api_key),
                key_mask=_mask_secret(settings.effective_llm_api_key),
            )

    if provider.credential is None and settings.effective_llm_api_key:
        repository.save_credential(
            provider_id=provider.id,
            encrypted_api_key=_encode_demo_secret(settings.effective_llm_api_key),
            key_mask=_mask_secret(settings.effective_llm_api_key),
        )

    profile = repository.get_default_profile(workspace_id=auth_context.workspace.id)
    if profile is None:
        profile = repository.create_profile(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            provider_id=provider.id,
            name="默认模型配置",
            chat_model=settings.effective_llm_model,
            embedding_model=settings.dashscope_embedding_model,
            temperature=settings.llm_temperature,
            max_tokens=2048,
            is_default=True,
        )

    _ensure_default_bindings(repository=repository, auth_context=auth_context, profile=profile)
    session.commit()
    return provider, profile


def _ensure_default_bindings(
    *,
    repository: ModelSettingsRepository,
    auth_context: AuthContext,
    profile: ModelProfile,
) -> None:
    """为首版内置 Agent 能力补齐默认模型绑定。"""

    existing = {
        (binding.agent_key, binding.capability)
        for binding in repository.list_bindings(workspace_id=auth_context.workspace.id)
    }
    for item in DEFAULT_AGENT_BINDINGS:
        key = (item["agent_key"], item["capability"])
        if key in existing:
            continue
        repository.upsert_binding(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
            agent_key=item["agent_key"],
            capability=item["capability"],
            model_profile_id=profile.id,
            enabled=True,
            params_json={},
        )


def _build_model_settings_payload(
    *,
    session: Session,
    provider: ModelProvider,
    profile: ModelProfile,
) -> ModelSettingsPayload:
    repository = ModelSettingsRepository(session)
    bindings = repository.list_bindings(workspace_id=provider.workspace_id)
    credential = provider.credential or session.scalar(
        select(ModelCredential).where(ModelCredential.provider_id == provider.id)
    )
    return ModelSettingsPayload(
        provider=ModelProviderPayload(
            id=provider.id,
            name=provider.name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            status=provider.status,
            api_key_saved=credential is not None,
            api_key_mask=credential.key_mask if credential else None,
            last_checked_at=provider.last_checked_at,
        ),
        profile=ModelProfilePayload(
            id=profile.id,
            name=profile.name,
            chat_model=profile.chat_model,
            embedding_model=profile.embedding_model,
            temperature=float(profile.temperature),
            max_tokens=profile.max_tokens,
            is_default=profile.is_default,
            status=profile.status,
        ),
        agent_bindings=[_binding_payload(binding) for binding in bindings],
    )


def _binding_payload(binding) -> AgentModelBindingPayload:
    labels = _binding_labels(binding.agent_key, binding.capability)
    return AgentModelBindingPayload(
        id=binding.id,
        agent_key=binding.agent_key,
        agent_label=labels["agent_label"],
        capability=binding.capability,
        capability_label=labels["capability_label"],
        model_profile_id=binding.model_profile_id,
        model_profile_name=binding.profile.name,
        enabled=binding.enabled,
        params=binding.params_json or {},
    )


def _binding_labels(agent_key: str, capability: str) -> dict[str, str]:
    for item in DEFAULT_AGENT_BINDINGS:
        if item["agent_key"] == agent_key and item["capability"] == capability:
            return {
                "agent_label": item["agent_label"],
                "capability_label": item["capability_label"],
            }
    return {"agent_label": agent_key, "capability_label": capability}


def _normalize_provider_type(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "dashscope": "dashscope",
        "aliyun": "dashscope",
        "openai": "openai",
        "deepseek": "deepseek",
        "local": "local",
        "本地兼容服务": "local",
    }
    if normalized not in mapping:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="暂不支持该模型供应商类型。")
    return mapping[normalized]


def _is_secret_placeholder(value: str | None) -> bool:
    return (value or "").strip() in SECRET_PLACEHOLDERS


def _encode_demo_secret(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return f"local-demo:{encoded}"


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return f"{value[:2]}****"
    return f"{value[:3]}****{value[-4:]}"
