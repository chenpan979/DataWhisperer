"""V4 多智能体编排模块。

这里放的是 DataWhisperer 的 Agent Harness。
V4.0 先做单库 Text-to-SQL 多智能体拆分，后续再扩展多库路由、MCP 工具和更完整的评测闭环。
"""

from app.agents.sql_of_thought import DataAnalysisOrchestrator

__all__ = ["DataAnalysisOrchestrator"]
