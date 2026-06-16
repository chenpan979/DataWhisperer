from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationRunRequest(BaseModel):
    """评测运行请求。

    suites 为空时表示运行全部套件。dataset_file_id 为空时使用内置评测集；
    传入上传文件 id 时，Text-to-SQL 套件会使用该文件中的自定义用例。
    """

    suites: list[str] = Field(default_factory=list, description="Evaluation suite ids to run.")
    dataset_file_id: str | None = Field(default=None, description="Uploaded evaluation dataset file id.")


class EvaluationKpi(BaseModel):
    """顶部质量指标卡。"""

    id: str
    label: str
    value: str
    description: str
    status: str = "ok"


class EvaluationSuiteSummary(BaseModel):
    """单个评测套件的汇总信息。"""

    id: str
    name: str
    description: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    duration_ms: int
    status: str


class EvaluationCaseResult(BaseModel):
    """单条评测明细。"""

    suite_id: str
    suite_name: str
    case_id: str
    title: str
    status: str
    question: str = ""
    expected: str = ""
    actual: str = ""
    errors: list[str] = Field(default_factory=list)
    generated_sql: str = ""
    tags: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class EvaluationVersionSnapshot(BaseModel):
    """用于前端展示版本质量趋势的轻量快照。"""

    version: str
    overall_pass_rate: float
    sql_executable_rate: float
    safety_pass_rate: float
    retrieval_pass_rate: float
    avg_latency_ms: int


class EvaluationTrendPoint(BaseModel):
    """质量趋势图中的一个版本点。"""

    version: str
    overall_pass_rate: float
    sql_quality_rate: float
    retrieval_pass_rate: float


class EvaluationIssueDistribution(BaseModel):
    """评测问题类型分布。"""

    name: str
    value: int
    status: str = "ok"


class EvaluationRecentRun(BaseModel):
    """最近评测任务摘要。"""

    id: str
    name: str
    suite: str
    status: str
    pass_rate: float
    case_count: int
    duration_ms: int
    finished_at: str


class EvaluationModelComparison(BaseModel):
    """模型/策略对比行。"""

    name: str
    scenario: str
    overall_pass_rate: float
    sql_quality_rate: float
    retrieval_pass_rate: float
    avg_latency_ms: int
    note: str


class EvaluationRunResponse(BaseModel):
    """评测中心主响应。"""

    run_id: str
    generated_at: str
    duration_ms: int
    dataset_file_id: str = ""
    dataset_name: str = "内置评测集"
    kpis: list[EvaluationKpi]
    suites: list[EvaluationSuiteSummary]
    cases: list[EvaluationCaseResult]
    version_snapshots: list[EvaluationVersionSnapshot]
    trend_points: list[EvaluationTrendPoint]
    issue_distribution: list[EvaluationIssueDistribution]
    recent_runs: list[EvaluationRecentRun]
    model_comparisons: list[EvaluationModelComparison]
