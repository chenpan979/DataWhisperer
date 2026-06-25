"""历史兼容入口。

`app.agent` 是 V1-V3 遗留路径；V4 之后真实多智能体实现放在
`app.agents` 目录。保留这个文件是为了让旧导入不报错，新代码请使用
`app.agents.orchestrator.DataAnalysisOrchestrator`。
"""

from app.agents.orchestrator import DataAnalysisOrchestrator
from app.agents.retrieval_context import combine_retrieval_contexts as _combine_retrieval_contexts
from app.agents.validation_execution import execute_safe_query
from app.agents.validation_execution import execute_with_optional_repair as _execute_with_optional_repair

__all__ = [
    "DataAnalysisOrchestrator",
    "_combine_retrieval_contexts",
    "_execute_with_optional_repair",
    "execute_safe_query",
]