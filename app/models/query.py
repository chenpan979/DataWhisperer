from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """自然语言查询接口的入参模型。

    这里不用普通 dict，而是用 Pydantic 模型，主要有三个好处：
    1. FastAPI 可以自动校验字段类型和范围；
    2. Swagger 文档会自动生成请求格式；
    3. 后续前端接入时，输入契约稳定，不容易传乱。
    """

    question: str = Field(
        min_length=2,
        description="Natural-language data question, for example: sales trend by month.",
    )
    max_rows: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum rows the API may return for this request.",
    )


class TraceStep(BaseModel):
    """Agent 执行过程中的一个可观测步骤。

    DataWhisperer 不只返回最终答案，也返回每一步做了什么。
    这对调试和面试展示都很重要：用户可以看到系统是否完成了
    读取 schema、生成 SQL、执行查询、生成图表、生成结论等步骤。
    """

    name: str = Field(description="Step name, such as schema, generate_sql, or chart.")
    status: str = Field(description="Step status, usually ok or failed.")
    detail: str | None = Field(default=None, description="Short human-readable detail.")


class QueryResponse(BaseModel):
    """Text-to-SQL Agent 的统一出参模型。

    返回值刻意拆成 SQL、表格、图表、分析结论和轨迹几块。
    这样前端可以直接分区域渲染，不需要从一大段自然语言里再解析结构化数据。
    """

    question: str = Field(description="Original user question.")
    generated_sql: str = Field(description="Final safe SQL that was executed.")
    sql_explanation: str = Field(description="Short explanation of what the SQL does.")
    columns: list[str] = Field(description="Result table column names.")
    rows: list[dict[str, Any]] = Field(description="Result table rows.")
    chart: dict[str, Any] = Field(description="ECharts-compatible chart option.")
    insight: str = Field(description="Concise business analysis based on returned rows.")
    warnings: list[str] = Field(default_factory=list)
    trace_steps: list[TraceStep] = Field(default_factory=list)
