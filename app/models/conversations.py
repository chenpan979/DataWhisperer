from typing import Any

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """一次问答轮次的持久化快照。

    后端保存的不只是问题和结论，还包括 SQL、表格数据、图表配置和前端回答卡片 HTML。
    这样用户刷新页面或重启后端后，可以恢复接近原始生成时的完整对话体验。
    """

    traceId: str = Field(description="本轮问答的唯一标识。")
    question: str = Field(description="用户提出的自然语言问题。")
    insight: str = Field(description="助手生成的业务分析结论。")
    rowCount: int = Field(default=0, description="本轮查询返回的行数。")
    columnCount: int = Field(default=0, description="本轮查询返回的字段数量。")
    chartType: str = Field(default="-", description="前端展示用的图表类型。")
    createdAt: str = Field(description="前端展示用的消息时间。")
    generatedSql: str = Field(default="", description="本轮实际执行的 SQL。")
    sqlExplanation: str = Field(default="", description="SQL 生成说明。")
    columns: list[str] = Field(default_factory=list, description="查询结果字段。")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="查询结果行数据。")
    chart: dict[str, Any] = Field(default_factory=dict, description="ECharts 图表配置。")
    warnings: list[str] = Field(default_factory=list, description="风险提示或兜底说明。")
    traceSteps: list[dict[str, Any]] = Field(default_factory=list, description="执行过程步骤。")
    followups: list[str] = Field(default_factory=list, description="后续追问建议。")
    assistantHtml: str = Field(default="", description="助手回答卡片的前端 HTML 快照。")


class Conversation(BaseModel):
    """AI 查数工作台中的一个会话。

    当前版本先落到本地 JSON 文件，便于单机演示和面试讲解。
    后续接入用户登录后，可以平滑迁移到 MySQL、PostgreSQL 或 Redis。
    """

    id: str = Field(description="会话 ID。")
    title: str = Field(default="新对话", description="左侧列表和顶部标题展示的会话名称。")
    subtitle: str = Field(default="等待数据问题", description="当前会话提炼出的生效条件。")
    preview: str = Field(default="等待数据问题", description="左侧列表中的摘要。")
    customTitle: bool = Field(default=False, description="用户是否手动重命名过会话。")
    updatedAt: int = Field(description="毫秒级更新时间戳，用于排序。")
    turns: list[ConversationTurn] = Field(default_factory=list, description="会话中的历史问答。")


class ConversationList(BaseModel):
    """会话列表响应。"""

    conversations: list[Conversation]
    activeConversationId: str | None = None


class ConversationCreate(BaseModel):
    """创建会话请求。"""

    title: str = "新对话"
    subtitle: str = "等待数据问题"
    preview: str = "等待数据问题"


class ConversationUpdate(BaseModel):
    """更新会话元信息请求。

    所有字段都是可选的，前端只需要提交发生变化的部分。
    """

    title: str | None = None
    subtitle: str | None = None
    preview: str | None = None
    customTitle: bool | None = None
    turns: list[ConversationTurn] | None = None
