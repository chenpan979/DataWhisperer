from __future__ import annotations

import base64
import time
from datetime import datetime
from typing import Annotated

import httpx
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
    ModelChatTestRequest,
    ModelConnectionTestResponse,
    ModelEndpointRequest,
    ModelListResponse,
    ModelProfilePayload,
    ModelProviderPayload,
    ModelSettingsPayload,
    ModelSettingsUpdateRequest,
)
from app.repositories.product import ModelSettingsRepository
from app.tools.agent_model_router import decode_model_api_key

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
        "agent_key": "query_planning_agent",
        "agent_label": "查询规划 Agent",
        "capability": "query_planning",
        "capability_label": "SQL-of-Thought 计划",
    },
    {
        "agent_key": "sql_correction_plan_agent",
        "agent_label": "SQL 纠错规划 Agent",
        "capability": "sql_correction_plan",
        "capability_label": "错误分类与修复计划",
    },
    {
        "agent_key": "sql_repair_agent",
        "agent_label": "SQL 修复 Agent",
        "capability": "sql_repair",
        "capability_label": "按计划重写 SQL",
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


@router.post("/default/models", response_model=ModelListResponse)
def list_provider_models(
    payload: ModelEndpointRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> ModelListResponse:
    """读取 OpenAI 兼容的模型列表，不修改表单配置。"""
    base_url, api_key = _resolve_probe_credentials(payload, auth_context, session)
    result = _probe_provider("GET", base_url, "models", api_key)
    data = result.get("data")
    if not isinstance(data, list):
        raise HTTPException(502, detail="模型列表接口未返回 OpenAI 兼容的 data 数组。")
    models = {
        item["id"].strip() for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
        and 0 < len(item["id"].strip()) <= 128 and api_key not in item["id"]
    }
    return ModelListResponse(models=sorted(models))


@router.post("/default/test", response_model=ModelConnectionTestResponse)
def test_default_model_settings(
    payload: ModelChatTestRequest,
    auth_context: Annotated[AuthContext, Depends(require_auth_context)],
    session: Session = Depends(get_product_session),
) -> ModelConnectionTestResponse:
    """使用当前表单发起一次最小 Chat 请求，不保存表单内容。"""
    started_at = time.perf_counter()
    model = payload.chat_model.strip()
    if not model:
        raise HTTPException(400, detail="请先选择或填写 Chat 模型。")
    base_url, api_key = _resolve_probe_credentials(payload, auth_context, session)
    try:
        result = _probe_provider(
            "POST", base_url, "chat/completions", api_key,
            body={"model": model, "messages": [{"role": "user", "content": "Reply OK."}],
                  "max_tokens": 16},
        )
        choices = result.get("choices")
        if not (isinstance(choices, list) and choices and isinstance(choices[0], dict)
                and isinstance(choices[0].get("message"), dict)):
            raise HTTPException(502, detail="Chat 接口未返回 OpenAI 兼容的模型回复。")
    except HTTPException as exc:
        ok, message = False, str(exc.detail)
    else:
        ok, message = True, "Chat 请求成功。测试未保存模型配置，也未测试 Embedding。"
    return ModelConnectionTestResponse(
        ok=ok, message=message, status="configured" if ok else "failed",
        latency_ms=max(1, round((time.perf_counter() - started_at) * 1000)),
        checked_at=datetime.now(),
    )


def _resolve_probe_credentials(
    payload: ModelEndpointRequest, auth_context: AuthContext, session: Session,
) -> tuple[str, str]:
    raw_url = payload.base_url.strip().rstrip("/")
    try:
        url = httpx.URL(raw_url)
    except httpx.InvalidURL as exc:
        raise HTTPException(400, detail="Base URL 格式不正确。") from exc
    if (url.scheme not in {"http", "https"} or not url.host or url.userinfo
            or "?" in raw_url or "#" in raw_url):
        raise HTTPException(400, detail="Base URL 必须是 HTTP(S) API 根地址，不能包含账号、查询参数或片段。")
    if url.path.lower().endswith(("/chat/completions", "/models", "/embeddings", "/responses")):
        raise HTTPException(400, detail="请填写 API 根地址（例如 https://中转站/v1），不要填具体接口路径。")

    base_url = str(url).rstrip("/")
    api_key = payload.api_key.get_secret_value().strip() if payload.api_key else ""
    if _is_secret_placeholder(api_key):
        provider, _ = _ensure_default_model_settings(session=session, auth_context=auth_context)
        if base_url != provider.base_url.strip().rstrip("/"):
            raise HTTPException(400, detail="Base URL 已更改，请输入该地址对应的 API Key 后再测试。")
        try:
            api_key = decode_model_api_key(provider.credential) or ""
        except ValueError:
            api_key = ""
    if not api_key:
        raise HTTPException(400, detail="请先填写模型 API Key。")
    return base_url, api_key


def _probe_provider(
    method: str, base_url: str, endpoint: str, api_key: str, *, body: dict | None = None,
) -> dict:
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.request(method, f"{base_url}/{endpoint}",
                                      headers={"Authorization": f"Bearer {api_key}"}, json=body)
    except httpx.TimeoutException as exc:
        raise HTTPException(502, detail=f"/{endpoint} 请求超时，请检查中转站和网络。") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(502, detail=f"/{endpoint} 请求无法发送，请检查地址、API Key 和网络。") from exc

    code = response.status_code
    if not response.is_success:
        reason = {
            401: "请核对 API Key。",
            403: "请核对 API Key 的权限或中转站访问限制。",
            404: ("请核对 Base URL；中转站也可能不提供模型列表，可手动填写模型名。"
                  if endpoint == "models" else "请核对 Base URL 和 Chat 模型 ID，确认中转站支持此接口。"),
            429: "请检查中转站限流和额度。",
        }.get(code, "请检查中转站配置和接口兼容性。")
        raise HTTPException(502, detail=f"/{endpoint} 请求失败（HTTP {code}）。{reason}")
    try:
        result = response.json()
    except ValueError:
        result = None
    if not isinstance(result, dict):
        raise HTTPException(502, detail=f"/{endpoint} 未返回 JSON 对象，请确认填的是 API 地址而非网页地址。")
    return result


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
