from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any


DEFAULT_PROMPT_VERSION = "v1"
DEFAULT_PROMPT_ROLES = ("system", "user")


class PromptTemplateError(RuntimeError):
    """提示词模板加载或渲染失败时抛出的异常。"""


@dataclass(frozen=True)
class PromptTemplate:
    """一个独立的提示词模板文件。

    prompt_id 表示业务用途，例如 sql_generation。
    version 表示模板版本，例如 v1。
    role 对应 Chat Completions 消息角色，例如 system 或 user。
    """

    prompt_id: str
    version: str
    role: str
    path: Path
    content: str

    @property
    def variables(self) -> tuple[str, ...]:
        """解析模板中声明的变量名。

        模板变量使用 Python format 风格，例如 {question}、{schema_prompt}。
        这里统一收集变量名，用于渲染前做缺失变量检查。
        """

        names: set[str] = set()
        for _, field_name, _, _ in Formatter().parse(self.content):
            if not field_name:
                continue
            # 只允许使用简单变量名。后续如果需要复杂表达式，应在代码里提前算好再传入。
            name = field_name.split(".", 1)[0].split("[", 1)[0]
            names.add(name)
        return tuple(sorted(names))

    def render(self, variables: Mapping[str, Any]) -> str:
        """把变量填入模板，并返回最终 prompt 文本。"""

        missing = [name for name in self.variables if name not in variables]
        if missing:
            missing_text = ", ".join(missing)
            raise PromptTemplateError(
                f"Prompt '{self.prompt_id}/{self.version}/{self.role}' missing variables: "
                f"{missing_text}"
            )
        return self.content.format(**variables)


@dataclass(frozen=True)
class PromptRenderResult:
    """一次提示词渲染的结构化结果。"""

    prompt_id: str
    version: str
    messages: list[dict[str, str]]
    variables: tuple[str, ...]
    template_paths: tuple[Path, ...]


class PromptRegistry:
    """提示词注册中心。

    V2 的核心目标之一是让 prompt 从代码里独立出来，具备版本化、可追踪、
    可回滚的能力。PromptRegistry 负责按 prompt_id/version/role 读取模板，
    渲染成大模型可直接使用的 messages。
    """

    def __init__(self, base_dir: str | Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.base_dir = Path(base_dir) if base_dir else project_root / "prompts"
        self._cache: dict[tuple[str, str, str], PromptTemplate] = {}

    def load_template(self, prompt_id: str, version: str, role: str) -> PromptTemplate:
        """加载单个模板文件。"""

        cache_key = (prompt_id, version, role)
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self.base_dir / prompt_id / version / f"{role}.md"
        if not path.exists():
            raise PromptTemplateError(f"Prompt template not found: {path}")

        template = PromptTemplate(
            prompt_id=prompt_id,
            version=version,
            role=role,
            path=path,
            content=path.read_text(encoding="utf-8").strip(),
        )
        self._cache[cache_key] = template
        return template

    def render_messages(
        self,
        prompt_id: str,
        variables: Mapping[str, Any],
        version: str = DEFAULT_PROMPT_VERSION,
        roles: Sequence[str] = DEFAULT_PROMPT_ROLES,
    ) -> PromptRenderResult:
        """把一个 prompt_id 下的多个 role 模板渲染成 Chat messages。"""

        templates = [self.load_template(prompt_id, version, role) for role in roles]
        messages = [
            {"role": template.role, "content": template.render(variables)}
            for template in templates
        ]
        used_variables = sorted({name for template in templates for name in template.variables})
        return PromptRenderResult(
            prompt_id=prompt_id,
            version=version,
            messages=messages,
            variables=tuple(used_variables),
            template_paths=tuple(template.path for template in templates),
        )


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    """返回进程内复用的 PromptRegistry。"""

    return PromptRegistry()
