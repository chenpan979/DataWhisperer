from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.core.llm import LLMClient
from app.models.query import QueryRequest, QueryResponse, TraceStep
from app.tools.chart_tool import recommend_chart
from app.tools.insight_tool import generate_insight
from app.tools.query_tool import execute_safe_query
from app.tools.schema_tool import build_schema_overview, schema_to_prompt
from app.tools.sql_tool import generate_sql


class DataAnalysisOrchestrator:
    """DataWhisperer 第一阶段的主控编排器。

    你可以把它理解成 V1 版本的 Agent Harness：
    它本身不直接写 SQL、不直接画图、不直接拼接数据库结果，
    而是把多个职责单一的工具按固定流程串起来。

    当前流程是：
    用户问题 -> 读取数据库结构 -> 生成 SQL -> 校验并执行 SQL -> 生成图表 -> 生成分析结论。

    这样做的好处是 API 层保持很薄，后续要演进多智能体时，
    可以从这里把 SQL Agent、Chart Agent、Insight Agent 逐步拆出去。
    """

    def __init__(self, engine: Engine, llm: LLMClient):
        self.engine = engine
        self.llm = llm
        self.settings = get_settings()

    async def run(self, request: QueryRequest) -> QueryResponse:
        """执行一次完整的自然语言数据分析请求。"""

        trace: list[TraceStep] = []
        warnings: list[str] = []

        # 第一步：读取数据库结构，并压缩成适合放进 prompt 的文本。
        # 大模型需要知道有哪些表、字段、外键关系，但不需要直接看到原始数据。
        schema = build_schema_overview(self.engine)
        schema_prompt = schema_to_prompt(schema)
        trace.append(TraceStep(name="schema", status="ok", detail=f"{schema['table_count']} tables"))

        # 第二步：生成 SQL。
        # 命中内置示例问题时优先走稳定规则；自由问题则交给大模型生成。
        # 这样既保证演示问题稳定，又保留真实 Text-to-SQL 能力。
        generated = await generate_sql(request.question, schema_prompt, self.llm)
        if generated.used_fallback:
            warnings.append("当前 SQL 由本地演示规则生成，用于保证示例问题稳定可运行。")
        trace.append(TraceStep(name="generate_sql", status="ok", detail=generated.explanation))

        # 第三步：执行 SQL 前再次做安全校验和行数限制。
        # 不能只依赖提示词约束模型，真正的安全边界必须在服务端代码里。
        max_rows = min(request.max_rows, self.settings.max_query_rows)
        safe_sql, columns, rows = execute_safe_query(self.engine, generated.sql, max_rows)
        trace.append(TraceStep(name="execute_sql", status="ok", detail=f"{len(rows)} rows"))

        # 第四步：根据真实查询结果生成图表配置。
        # 图表推荐先用确定性规则实现，比完全依赖模型更稳定。
        chart = recommend_chart(columns, rows, question=request.question)
        trace.append(TraceStep(name="chart", status="ok", detail=chart.get("type", "unknown")))

        # 第五步：基于查询结果生成业务结论。
        # 结论必须在 SQL 执行之后生成，避免模型脱离数据凭空分析。
        insight = await generate_insight(request.question, safe_sql, columns, rows, self.llm)
        trace.append(TraceStep(name="insight", status="ok"))

        return QueryResponse(
            question=request.question,
            generated_sql=safe_sql,
            sql_explanation=generated.explanation,
            columns=columns,
            rows=rows,
            chart=chart,
            insight=insight,
            warnings=warnings,
            trace_steps=trace,
        )
