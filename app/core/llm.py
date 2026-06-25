import json
from typing import Any

from app.core.config import Settings, get_settings


class LLMClient:
    """OpenAI-compatible 大模型客户端封装。

    项目内部不要到处直接调用某个厂商 SDK，而是统一经过这个类。
    只要外部模型服务兼容 OpenAI Chat Completions 协议，就可以通过
    base_url、api_key、model 三个配置接入，例如 DashScope/Qwen、DeepSeek、
    OpenAI 或公司内部模型网关。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.settings = settings or get_settings()
        self.base_url = base_url or self.settings.effective_llm_base_url
        self.api_key = api_key if api_key is not None else self.settings.effective_llm_api_key
        self.model = model or self.settings.effective_llm_model
        self.temperature = temperature if temperature is not None else self.settings.llm_temperature
        self.max_tokens = max_tokens
        self._client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - environment setup guard
                raise RuntimeError(
                    "The 'openai' package is required when LLM_API_KEY is configured. "
                    "Install dependencies with: pip install -e ."
                ) from exc
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    @property
    def enabled(self) -> bool:
        """当前进程是否已经初始化远程大模型客户端。"""

        return self._client is not None

    async def complete_text(self, messages: list[dict[str, str]]) -> str | None:
        """调用大模型并返回文本。

        如果没有配置 API Key，则返回 None，让上层走本地演示规则。
        """

        if not self._client:
            return None
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens:
            request_kwargs["max_tokens"] = self.max_tokens
        response = await self._client.chat.completions.create(**request_kwargs)
        return response.choices[0].message.content or ""

    async def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        """调用大模型并尽量解析 JSON 对象。

        模型有时会把 JSON 包在 Markdown 代码块里，或者前后带解释文字。
        这里做一点容错，提升 Text-to-SQL 链路的稳定性。
        """

        text = await self.complete_text(messages)
        if not text:
            return None
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise


def get_llm_client() -> LLMClient:
    return LLMClient()
