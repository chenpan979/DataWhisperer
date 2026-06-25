"""DataWhisperer V4 多智能体模块。

`app.agents` 是当前真实使用的多智能体实现目录；`app.agent` 只保留
历史兼容入口。业务入口优先从这里导入 Orchestrator 或具体 Agent。
"""

from app.agents.orchestrator import DataAnalysisOrchestrator

__all__ = ["DataAnalysisOrchestrator"]