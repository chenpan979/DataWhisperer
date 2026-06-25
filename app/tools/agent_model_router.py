from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.llm import LLMClient
from app.db.product_models import AgentModelBinding, ModelCredential
from app.repositories.product import ModelSettingsRepository


@dataclass(frozen=True)
class AgentModelRoute:
    """Resolved model profile for one agent binding."""

    agent_key: str
    capability: str
    provider_name: str
    provider_type: str
    profile_name: str
    chat_model: str
    embedding_model: str | None
    base_url: str
    temperature: float
    max_tokens: int
    enabled: bool
    has_api_key: bool

    @property
    def trace_label(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"model={self.provider_name}/{self.chat_model}, profile={self.profile_name}, {status}"


class AgentModelRouter:
    """Route each Agent to its configured model client.

    The router keeps the public query response stable: agents still emit the old
    trace step names, while the trace detail can show which profile was used.
    """

    def __init__(
        self,
        *,
        default_llm: Any,
        clients: dict[str, Any] | None = None,
        routes: dict[str, AgentModelRoute] | None = None,
    ):
        self.default_llm = default_llm
        self.clients = clients or {}
        self.routes = routes or {}

    def client_for(self, agent_key: str) -> Any:
        """Return the configured client for one agent, or the runtime default."""

        return self.clients.get(agent_key, self.default_llm)

    def trace_detail(self, agent_key: str) -> str:
        """Return a compact trace label for observability."""

        route = self.routes.get(agent_key)
        if route is None:
            return "model=runtime-default"
        return route.trace_label


def build_agent_model_router(
    *,
    session: Session,
    auth_context: Any | None,
    fallback_llm: Any,
    client_factory: Callable[..., Any] = LLMClient,
) -> AgentModelRouter:
    """Resolve workspace agent bindings into runtime model clients."""

    if auth_context is None:
        return AgentModelRouter(default_llm=fallback_llm)

    repository = ModelSettingsRepository(session)
    bindings = repository.list_bindings(workspace_id=auth_context.workspace.id)
    clients: dict[str, Any] = {}
    routes: dict[str, AgentModelRoute] = {}

    for binding in bindings:
        route = _route_from_binding(binding)
        routes[binding.agent_key] = route
        if not route.enabled or binding.capability == "embedding" or not route.has_api_key:
            continue
        clients[binding.agent_key] = client_factory(
            base_url=route.base_url,
            api_key=_decode_api_key(binding.profile.provider.credential),
            model=route.chat_model,
            temperature=route.temperature,
            max_tokens=route.max_tokens,
        )

    return AgentModelRouter(default_llm=fallback_llm, clients=clients, routes=routes)


def _route_from_binding(binding: AgentModelBinding) -> AgentModelRoute:
    profile = binding.profile
    provider = profile.provider
    params = binding.params_json or {}
    return AgentModelRoute(
        agent_key=binding.agent_key,
        capability=binding.capability,
        provider_name=provider.name,
        provider_type=provider.provider_type,
        profile_name=profile.name,
        chat_model=str(params.get("chat_model") or profile.chat_model),
        embedding_model=profile.embedding_model,
        base_url=provider.base_url,
        temperature=_float_param(params.get("temperature"), float(profile.temperature)),
        max_tokens=_int_param(params.get("max_tokens"), profile.max_tokens),
        enabled=binding.enabled,
        has_api_key=_decode_api_key(provider.credential) is not None,
    )


def _decode_api_key(credential: ModelCredential | None) -> str | None:
    if credential is None:
        return None
    value = credential.encrypted_api_key
    if not value:
        return None
    if value.startswith("local-demo:"):
        encoded = value.split(":", 1)[1]
        return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    return value


def _float_param(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int_param(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback