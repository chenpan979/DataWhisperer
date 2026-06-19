from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """一次问答轮次的持久化摘要。

    这里不保存完整查询结果，主要保存左侧历史列表和切回会话时最需要展示的信息。
    完整结果包含表格、图表和 SQL，体积会更大，后续可以按需拆成独立的结果快照表。
    """

    traceId: str = Field(description="本轮问答的唯一标识。")
    question: str = Field(description="用户提出的自然语言问题。")
    insight: str = Field(description="助手生成的业务分析结论。")
    rowCount: int = Field(default=0, description="本轮查询返回的行数。")
    columnCount: int = Field(default=0, description="本轮查询返回的字段数。")
    chartType: str = Field(default="-", description="前端展示用的图表类型。")
    createdAt: str = Field(description="前端展示用的消息时间。")


class Conversation(BaseModel):
    """AI 查数工作台中的一个会话。

    会话属于产品侧状态，和示例业务数据库解耦。当前版本先落到本地 JSON 文件，
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

