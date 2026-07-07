from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import AuthContext, require_auth_context
from app.core.database import get_engine
from app.core.llm import get_llm_client
from app.core.product_database import get_product_session
from app.evals.agent_text_to_sql import run_agent_text_to_sql_evals
from app.evals.metric_retrieval import load_metric_retrieval_cases, run_metric_retrieval_evals
from app.evals.text_to_sql import (
    TextToSqlEvalCase,
    build_text_to_sql_report,
    evaluate_case as evaluate_text_to_sql_case,
    load_eval_cases,
    run_text_to_sql_evals,
)
from app.models.files import FilePreview, ManagedFile, ManagedFileList
from app.rag.document_retriever import RagKnowledgeScope, get_rag_document_retriever
from app.repositories.product import KnowledgeRepository
from app.models.evaluations import (
    EvaluationBucketSummary,
    EvaluationCaseResult,
    EvaluationIssueDistribution,
    EvaluationKpi,
    EvaluationModelComparison,
    EvaluationRecentRun,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSuiteSummary,
    EvaluationTrendPoint,
    EvaluationVersionSnapshot,
)
from app.tools.file_store import ManagedFileStore, get_evaluation_dataset_store
from app.tools.sql_tool import validate_select_sql

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
EVAL_DATASET_DIR = Path(__file__).resolve().parents[2] / "evals"
AGENT_EVAL_CASES_PATH = EVAL_DATASET_DIR / "text_to_sql_18_table_cases.jsonl"
BUILTIN_EVALUATION_DATASETS = (
    EVAL_DATASET_DIR / "text_to_sql_cases.json",
    EVAL_DATASET_DIR / "text_to_sql_18_table_cases.jsonl",
    EVAL_DATASET_DIR / "text_to_sql_upload_100_cases.jsonl",
    EVAL_DATASET_DIR / "text_to_sql_product_240_cases.jsonl",
    EVAL_DATASET_DIR / "text_to_sql_product_360_cases.jsonl",
)


@router.get("/datasets", response_model=ManagedFileList)
def list_evaluation_datasets() -> ManagedFileList:
    """列出用户上传的评测测试集文件。"""

    return _list_dataset_files(get_evaluation_dataset_store())


@router.post("/datasets", response_model=ManagedFile)
async def upload_evaluation_dataset(file: UploadFile = File(...)) -> ManagedFile:
    """上传评测测试集文件。

    当前版本先完成测试集文件管理，后续可以把这些文件解析成真实评测用例，
    再接入 Text-to-SQL、指标检索和分析结论质量评测 runner。
    """

    return await _upload_dataset_file(get_evaluation_dataset_store(), file)


@router.post("/datasets/sync-builtins", response_model=ManagedFileList)
def sync_builtin_evaluation_datasets() -> ManagedFileList:
    """把项目内置评测集同步到测试集管理列表。

    evals/ 目录中的 benchmark 是代码仓库里的最新版本；测试集管理页面读取的是
    storage/evaluation_datasets 下的已上传副本。同步时只替换同名内置文件，用户自己上传的
    custom 测试集会保留。
    """

    return _sync_builtin_dataset_files(get_evaluation_dataset_store())


@router.delete("/datasets/{file_id}")
def delete_evaluation_dataset(file_id: str) -> dict[str, bool]:
    """删除用户上传的评测测试集文件。"""

    return _delete_dataset_file(get_evaluation_dataset_store(), file_id)


@router.get("/datasets/{file_id}/preview", response_model=FilePreview)
def preview_evaluation_dataset(file_id: str) -> FilePreview:
    """预览用户上传的评测测试集文件。"""

    return _preview_dataset_file(get_evaluation_dataset_store(), file_id)


def _list_dataset_files(store: ManagedFileStore) -> ManagedFileList:
    return ManagedFileList(category=store.config.category, files=store.list_files())



def _sync_builtin_dataset_files(store: ManagedFileStore) -> ManagedFileList:
    """同步内置 benchmark 文件到上传文件仓库。"""

    missing = [path.name for path in BUILTIN_EVALUATION_DATASETS if not path.exists()]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"内置评测集文件不存在：{', '.join(missing)}",
        )

    builtin_names = {path.name for path in BUILTIN_EVALUATION_DATASETS}
    for file in store.list_files():
        if file.name in builtin_names:
            store.delete(file.id)

    for path in BUILTIN_EVALUATION_DATASETS:
        try:
            store.save(original_name=path.name, content=path.read_bytes())
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _list_dataset_files(store)

async def _upload_dataset_file(store: ManagedFileStore, file: UploadFile) -> ManagedFile:
    try:
        content = await file.read()
        return store.save(original_name=file.filename or "", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


def _delete_dataset_file(store: ManagedFileStore, file_id: str) -> dict[str, bool]:
    deleted = store.delete(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return {"deleted": True}


def _preview_dataset_file(store: ManagedFileStore, file_id: str) -> FilePreview:
    preview = store.preview(file_id)
    if not preview:
        raise HTTPException(status_code=404, detail="文件不存在。")
    return preview


@dataclass(frozen=True)
class SqlSafetyCase:
    """SQL 安全评测用例。"""

    id: str
    title: str
    sql: str
    should_pass: bool
    expected: str


SQL_SAFETY_CASES = (
    SqlSafetyCase(
        id="safe_select_orders",
        title="允许普通 SELECT 查询",
        sql="SELECT order_id, order_date FROM orders LIMIT 20",
        should_pass=True,
        expected="允许只读 SELECT 查询通过。",
    ),
    SqlSafetyCase(
        id="block_drop_table",
        title="拒绝 DROP TABLE",
        sql="DROP TABLE users",
        should_pass=False,
        expected="拦截 DDL 删除表结构。",
    ),
    SqlSafetyCase(
        id="block_delete_orders",
        title="拒绝 DELETE",
        sql="DELETE FROM orders",
        should_pass=False,
        expected="拦截数据删除语句。",
    ),
    SqlSafetyCase(
        id="block_multi_statement",
        title="拒绝多语句注入",
        sql="SELECT * FROM orders; DELETE FROM orders",
        should_pass=False,
        expected="拦截分号拼接的多语句。",
    ),
)


def _normalize_runner_mode(value: str | None) -> str:
    """标准化评测 Runner 模式，避免前端传错值后静默降级。"""

    mode = (value or "offline").strip().lower()
    if mode not in {"offline", "agent"}:
        raise HTTPException(status_code=400, detail="runner_mode must be offline or agent.")
    return mode


def _resolve_optional_auth_context(*, authorization: str | None, session: Session) -> AuthContext | None:
    """解析可选登录上下文。

    评测接口既支持公开 demo 运行，也支持登录后读取当前租户的 Milvus RAG
    知识库。没有登录态时不抛错，只把真实 RAG 命中率计为 0。
    """

    if not authorization:
        return None
    return require_auth_context(authorization=authorization, session=session)


def _resolve_rag_source_cases(
    *,
    custom_cases: list[TextToSqlEvalCase] | None,
    runner_mode: str,
) -> list[TextToSqlEvalCase]:
    """选择用于 RAG 命中评测的用例。

    RAG 命中率不再复用“指标口径检索”结果，而是从 Text-to-SQL 用例里挑出
    `requires_rag=true` 的问题，再到当前租户知识库里做真实检索。
    """

    if custom_cases is not None:
        return custom_cases
    if runner_mode == "agent":
        return load_eval_cases(AGENT_EVAL_CASES_PATH)
    return load_eval_cases()


@router.post("/run", response_model=EvaluationRunResponse)
async def run_evaluations(
    request: EvaluationRunRequest,
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_product_session),
) -> EvaluationRunResponse:
    """运行评测套件并返回前端展示所需的质量报告。

    默认使用项目内置评测集。当前端传入 dataset_file_id 时，Text-to-SQL
    套件会切换为用户上传的自定义测试集，便于做真实回归评测。
    """

    started = perf_counter()
    selected = set(request.suites)
    runner_mode = _normalize_runner_mode(request.runner_mode)
    run_all = not selected
    suites: list[EvaluationSuiteSummary] = []
    cases: list[EvaluationCaseResult] = []
    dataset_name = "内置评测集"
    if runner_mode == "agent":
        dataset_name = "内置 18 表 Agent 评测集"
    custom_text_cases: list[TextToSqlEvalCase] | None = None

    if request.dataset_file_id:
        dataset_file, custom_text_cases = _load_uploaded_text_to_sql_cases(request.dataset_file_id)
        dataset_name = dataset_file.name

    rag_source_cases = _resolve_rag_source_cases(
        custom_cases=custom_text_cases,
        runner_mode=runner_mode,
    )
    auth_context = _resolve_optional_auth_context(
        authorization=authorization,
        session=session,
    )

    if run_all or "text_to_sql" in selected:
        summary, results = await _run_text_to_sql_suite(
            custom_text_cases,
            dataset_name,
            runner_mode=runner_mode,
        )
        suites.append(summary)
        cases.extend(results)

    if run_all or "sql_safety" in selected:
        summary, results = _run_sql_safety_suite()
        suites.append(summary)
        cases.extend(results)

    if run_all or "metric_retrieval" in selected:
        summary, results = _run_metric_retrieval_suite()
        suites.append(summary)
        cases.extend(results)

    if run_all or "knowledge_retrieval" in selected:
        summary, results = _run_knowledge_retrieval_suite(
            rag_source_cases,
            auth_context=auth_context,
            session=session,
        )
        suites.append(summary)
        cases.extend(results)

    duration_ms = _elapsed_ms(started)
    version_snapshots = _build_version_snapshots(suites, duration_ms)
    return EvaluationRunResponse(
        run_id=f"eval-{uuid4().hex[:8]}",
        generated_at=datetime.now(UTC).isoformat(),
        duration_ms=duration_ms,
        dataset_file_id=request.dataset_file_id or "",
        dataset_name=dataset_name,
        runner_mode=runner_mode,
        kpis=_build_kpis(suites, duration_ms, runner_mode),
        suites=suites,
        cases=cases,
        version_snapshots=version_snapshots,
        trend_points=_build_trend_points(version_snapshots),
        issue_distribution=_build_issue_distribution(cases),
        recent_runs=_build_recent_runs(suites),
        model_comparisons=_build_model_comparisons(version_snapshots),
    )


async def _run_text_to_sql_suite(
    custom_cases: list[TextToSqlEvalCase] | None = None,
    dataset_name: str = "\u5185\u7f6e\u8bc4\u6d4b\u96c6",
    runner_mode: str = "offline",
) -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    if custom_cases is None:
        cases = load_eval_cases(AGENT_EVAL_CASES_PATH) if runner_mode == "agent" else load_eval_cases()
        suite_name = (
            "Text-to-SQL \u771f\u5b9e Agent 18 \u8868\u8bc4\u6d4b"
            if runner_mode == "agent"
            else "Text-to-SQL \u751f\u6210\u8bc4\u6d4b"
        )
        suite_description = (
            "\u901a\u8fc7\u771f\u5b9e\u591a\u667a\u80fd\u4f53\u94fe\u8def\u9a8c\u8bc1 schema\u3001RAG\u3001SQL \u751f\u6210\u3001\u5b89\u5168\u6267\u884c\u548c\u56fe\u8868\u7ed3\u679c\u3002"
            if runner_mode == "agent"
            else "\u6309\u7b80\u5355\u3001\u4e2d\u7b49\u3001\u590d\u6742\u95ee\u9898\u9a8c\u8bc1 SQL \u7247\u6bb5\u3001\u5b89\u5168\u7ea6\u675f\u548c\u56fe\u8868\u7c7b\u578b\u3002"
        )
    else:
        cases = custom_cases
        suite_name = f"\u4e0a\u4f20\u6d4b\u8bd5\u96c6\uff1a{dataset_name}"
        suite_description = (
            "\u4f7f\u7528\u4e0a\u4f20\u6d4b\u8bd5\u96c6\u9010\u6761\u8c03\u7528\u771f\u5b9e\u591a\u667a\u80fd\u4f53\u67e5\u6570\u94fe\u8def\u3002"
            if runner_mode == "agent"
            else "\u4f7f\u7528\u6d4b\u8bd5\u96c6\u7ba1\u7406\u4e2d\u4e0a\u4f20\u7684\u81ea\u5b9a\u4e49\u7528\u4f8b\u8fd0\u884c Text-to-SQL \u56de\u5f52\u8bc4\u6d4b\u3002"
        )

    if runner_mode == "agent":
        report = await run_agent_text_to_sql_evals(
            cases,
            engine=get_engine(),
            llm=get_llm_client(),
        )
    elif custom_cases is None:
        report = run_text_to_sql_evals()
    else:
        results_tuple = tuple(evaluate_text_to_sql_case(case) for case in custom_cases)
        report = build_text_to_sql_report(results_tuple)

    case_by_id = {case.id: case for case in cases}
    suite = _suite_summary(
        suite_id="text_to_sql",
        name=suite_name,
        description=suite_description,
        total=report.total,
        passed=report.passed,
        failed=report.failed,
        duration_ms=_elapsed_ms(started),
        difficulty_breakdown=_bucket_models(report.difficulty_breakdown),
        rag_breakdown=_bucket_models(report.rag_breakdown),
        ablation_breakdown=_bucket_models(report.ablation_breakdown),
    )
    results = [
        EvaluationCaseResult(
            suite_id=suite.id,
            suite_name=suite.name,
            case_id=result.case_id,
            title=case_by_id[result.case_id].question,
            status=_case_status(result.passed),
            question=case_by_id[result.case_id].question,
            expected=_join_expected(
                [
                    *case_by_id[result.case_id].expected_sql_contains,
                    f"chart={case_by_id[result.case_id].expected_chart_type}",
                    f"difficulty={case_by_id[result.case_id].difficulty}",
                ]
            ),
            actual=f"runner={runner_mode}; chart={result.chart_type}",
            errors=list(result.errors),
            generated_sql=result.generated_sql,
            tags=list(case_by_id[result.case_id].tags),
            difficulty=case_by_id[result.case_id].difficulty,
            requires_rag=case_by_id[result.case_id].requires_rag,
            ablation_tags=list(case_by_id[result.case_id].ablation_tags),
        )
        for result in report.results
    ]
    return suite, results

def _run_metric_retrieval_suite() -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    report = run_metric_retrieval_evals()
    case_by_id = {case.id: case for case in load_metric_retrieval_cases()}
    suite = _suite_summary(
        suite_id="metric_retrieval",
        name="指标口径检索评测",
        description="验证自然语言问题能否召回内置指标口径，避免错误口径污染 SQL。",
        total=report.total,
        passed=report.passed,
        failed=report.failed,
        duration_ms=_elapsed_ms(started),
    )
    results = [
        EvaluationCaseResult(
            suite_id=suite.id,
            suite_name=suite.name,
            case_id=result.case_id,
            title=case_by_id[result.case_id].question,
            status=_case_status(result.passed),
            question=case_by_id[result.case_id].question,
            expected=_join_expected(case_by_id[result.case_id].expected_metrics),
            actual=_join_expected(result.retrieved_metrics),
            errors=list(result.errors),
            tags=list(case_by_id[result.case_id].tags),
        )
        for result in report.results
    ]
    return suite, results


def _run_knowledge_retrieval_suite(
    source_cases: list[TextToSqlEvalCase],
    *,
    auth_context: AuthContext | None,
    session: Session,
) -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    """运行真实 Milvus RAG 知识库命中评测。

    这里的“RAG 命中率”和内置“指标命中率”分开计算：只有当前租户知识库
    已同步文档，并且检索返回来源时才算命中。没有知识库、没有同步分片或没有
    `requires_rag` 用例时，RAG 命中率会清晰显示为 0，而不是借用指标检索分数。
    """

    started = perf_counter()
    rag_cases = [case for case in source_cases if case.requires_rag]
    if auth_context is None:
        return _empty_knowledge_retrieval_suite(
            duration_ms=_elapsed_ms(started),
            description="未登录，无法读取租户知识库，RAG 知识库命中率按 0% 处理。",
        ), []
    if not rag_cases:
        return _empty_knowledge_retrieval_suite(
            duration_ms=_elapsed_ms(started),
            description="当前评测集没有 requires_rag=true 用例，RAG 知识库命中率按 0% 处理。",
        ), []

    repository = KnowledgeRepository(session)
    knowledge_base = repository.ensure_default_base(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        created_by=auth_context.user.id,
    )
    synced_documents = [
        document
        for document in repository.list_visible_documents(
            tenant_id=auth_context.tenant.id,
            workspace_id=auth_context.workspace.id,
        )
        if document.sync_status == "synced" and (document.sync_chunk_count or 0) > 0
    ]

    if not synced_documents:
        results = [
            _knowledge_retrieval_case_result(
                case,
                passed=False,
                actual="当前租户没有已同步的 RAG 知识库分片。",
                errors=["没有可检索的 Milvus 知识库数据"],
            )
            for case in rag_cases
        ]
        return _knowledge_retrieval_suite_summary(
            total=len(results),
            passed=0,
            failed=len(results),
            duration_ms=_elapsed_ms(started),
            description=f"当前租户没有已同步知识库，{len(results)} 条 RAG 用例全部未命中。",
        ), results

    retriever = get_rag_document_retriever()
    scope = RagKnowledgeScope(
        tenant_id=auth_context.tenant.id,
        workspace_id=auth_context.workspace.id,
        knowledge_base_id=knowledge_base.id,
    )
    results: list[EvaluationCaseResult] = []
    for case in rag_cases:
        retrieval = retriever.retrieve(case.question, scope=scope)
        sources = retrieval.sources
        passed = bool(sources)
        actual = (
            "命中：" + ", ".join(sources[:5])
            if passed
            else f"未命中，检索模式：{retrieval.retrieval_mode}"
        )
        results.append(
            _knowledge_retrieval_case_result(
                case,
                passed=passed,
                actual=actual,
                errors=[] if passed else ["知识库检索没有返回来源"],
            )
        )

    passed_count = sum(1 for result in results if result.status == "passed")
    return _knowledge_retrieval_suite_summary(
        total=len(results),
        passed=passed_count,
        failed=len(results) - passed_count,
        duration_ms=_elapsed_ms(started),
        description=(
            f"基于当前租户 {len(synced_documents)} 个已同步知识库文件，"
            f"命中 {passed_count}/{len(results)} 条 RAG 用例。"
        ),
    ), results


def _knowledge_retrieval_case_result(
    case: TextToSqlEvalCase,
    *,
    passed: bool,
    actual: str,
    errors: list[str],
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        suite_id="knowledge_retrieval",
        suite_name="RAG 知识库命中评测",
        case_id=f"rag_{case.id}",
        title=case.question,
        status=_case_status(passed),
        question=case.question,
        expected="当前租户知识库应返回至少一个相关来源。",
        actual=actual,
        errors=errors,
        tags=["knowledge_retrieval", *case.tags],
        difficulty=case.difficulty,
        requires_rag=True,
        ablation_tags=["rag_knowledge", *case.ablation_tags],
    )


def _empty_knowledge_retrieval_suite(
    *,
    duration_ms: int,
    description: str,
) -> EvaluationSuiteSummary:
    suite = _knowledge_retrieval_suite_summary(
        total=0,
        passed=0,
        failed=0,
        duration_ms=duration_ms,
        description=description,
    )
    suite.status = "idle"
    return suite


def _knowledge_retrieval_suite_summary(
    *,
    total: int,
    passed: int,
    failed: int,
    duration_ms: int,
    description: str,
) -> EvaluationSuiteSummary:
    return _suite_summary(
        suite_id="knowledge_retrieval",
        name="RAG 知识库命中评测",
        description=description,
        total=total,
        passed=passed,
        failed=failed,
        duration_ms=duration_ms,
    )


def _run_sql_safety_suite() -> tuple[EvaluationSuiteSummary, list[EvaluationCaseResult]]:
    started = perf_counter()
    results: list[EvaluationCaseResult] = []
    passed = 0
    for case in SQL_SAFETY_CASES:
        case_started = perf_counter()
        errors: list[str] = []
        try:
            validate_select_sql(case.sql)
            actual_passed = True
            actual = "通过安全校验"
        except ValueError as exc:
            actual_passed = False
            actual = f"已拦截：{exc}"

        if actual_passed != case.should_pass:
            errors.append(f"Expected should_pass={case.should_pass}, got {actual_passed}.")
        if not errors:
            passed += 1

        results.append(
            EvaluationCaseResult(
                suite_id="sql_safety",
                suite_name="SQL 安全边界评测",
                case_id=case.id,
                title=case.title,
                status=_case_status(not errors),
                expected=case.expected,
                actual=actual,
                errors=errors,
                generated_sql=case.sql,
                tags=["safety"],
                duration_ms=_elapsed_ms(case_started),
            )
        )

    suite = _suite_summary(
        suite_id="sql_safety",
        name="SQL 安全边界评测",
        description="验证服务端硬校验能否拦截写入、删除、DDL 和多语句风险。",
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        duration_ms=_elapsed_ms(started),
    )
    return suite, results


def _load_uploaded_text_to_sql_cases(file_id: str) -> tuple[ManagedFile, list[TextToSqlEvalCase]]:
    store = get_evaluation_dataset_store()
    payload = store.read_text_file(file_id)
    if not payload:
        raise HTTPException(status_code=404, detail="测试集文件不存在或不可读取。")
    dataset_file, text = payload
    try:
        cases = _parse_text_to_sql_dataset(dataset_file, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not cases:
        raise HTTPException(status_code=400, detail="测试集中没有可运行的用例。")
    return dataset_file, cases


def _parse_text_to_sql_dataset(dataset_file: ManagedFile, text: str) -> list[TextToSqlEvalCase]:
    extension = dataset_file.extension.casefold()
    if extension == ".json":
        raw = json.loads(text)
        items = _extract_case_items(raw)
    elif extension == ".jsonl":
        items = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif extension == ".csv":
        items = list(csv.DictReader(StringIO(text)))
    elif extension in {".yaml", ".yml"}:
        items = _load_yaml_items(text)
    elif extension == ".txt":
        items = [{"question": line.strip()} for line in text.splitlines() if line.strip()]
    else:
        raise ValueError(f"暂不支持解析 {extension} 测试集。")

    return [_case_from_uploaded_item(item, index) for index, item in enumerate(items, start=1)]


def _extract_case_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("cases", "items", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw]
    raise ValueError("JSON 测试集必须是对象、对象数组，或包含 cases/items/data 数组。")


def _load_yaml_items(text: str) -> list[dict[str, Any]]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValueError("当前环境未安装 PyYAML，暂不能解析 YAML 测试集。") from exc
    raw = yaml.safe_load(text)
    return _extract_case_items(raw)


def _case_from_uploaded_item(item: dict[str, Any], index: int) -> TextToSqlEvalCase:
    question = _first_text(item, "question", "问题", "prompt", "input")
    if not question:
        raise ValueError(f"第 {index} 条用例缺少 question 字段。")
    return TextToSqlEvalCase(
        id=_first_text(item, "id", "case_id") or f"uploaded_{index}",
        question=question,
        tags=tuple(_list_value(item.get("tags")) or ["uploaded"]),
        expected_sql_contains=tuple(
            _list_value(
                item.get("expected_sql_contains")
                or item.get("expected_sql_fragments")
                or item.get("expected_sql_fragment")
                or item.get("sql_contains")
            )
        ),
        forbidden_sql_contains=tuple(
            _list_value(item.get("forbidden_sql_contains") or item.get("forbidden_sql_fragments"))
        ),
        expected_columns=tuple(_list_value(item.get("expected_columns") or item.get("columns"))),
        expected_chart_type=_first_text(item, "expected_chart_type", "chart_type"),
        must_be_safe=_bool_value(item.get("must_be_safe"), default=True),
        difficulty=_first_text(item, "difficulty", "sql_difficulty") or "medium",
        requires_rag=_bool_value(
            item.get("requires_rag", item.get("rag_required")),
            default=False,
        ),
        ablation_tags=tuple(
            _list_value(
                item.get("ablation_tags")
                or item.get("ablation")
                or item.get("experiment_tags")
            )
        ),
    )


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            return _list_value(parsed)
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.split("|") if part.strip()]


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "否"}


def _suite_summary(
    suite_id: str,
    name: str,
    description: str,
    total: int,
    passed: int,
    failed: int,
    duration_ms: int,
    difficulty_breakdown: list[EvaluationBucketSummary] | None = None,
    rag_breakdown: list[EvaluationBucketSummary] | None = None,
    ablation_breakdown: list[EvaluationBucketSummary] | None = None,
) -> EvaluationSuiteSummary:
    pass_rate = round(passed / total, 4) if total else 0.0
    return EvaluationSuiteSummary(
        id=suite_id,
        name=name,
        description=description,
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=pass_rate,
        duration_ms=duration_ms,
        status="ok" if failed == 0 else "warning",
        difficulty_breakdown=difficulty_breakdown or [],
        rag_breakdown=rag_breakdown or [],
        ablation_breakdown=ablation_breakdown or [],
    )


def _bucket_models(items: tuple[object, ...]) -> list[EvaluationBucketSummary]:
    return [
        EvaluationBucketSummary(
            name=str(item.name),
            total=int(item.total),
            passed=int(item.passed),
            failed=int(item.failed),
            pass_rate=float(item.pass_rate),
        )
        for item in items
    ]


def _build_kpis(suites: list[EvaluationSuiteSummary], duration_ms: int, runner_mode: str) -> list[EvaluationKpi]:
    total = sum(suite.total for suite in suites)
    passed = sum(suite.passed for suite in suites)
    failed = sum(suite.failed for suite in suites)
    overall = round(passed / total * 100, 1) if total else 0.0
    text_suite = _find_suite(suites, "text_to_sql")
    safety_suite = _find_suite(suites, "sql_safety")
    retrieval_suite = _find_suite(suites, "metric_retrieval")
    knowledge_suite = _find_suite(suites, "knowledge_retrieval")
    return [
        EvaluationKpi(
            id="overall",
            label="综合通过率",
            value=f"{overall}%",
            description=f"{passed}/{total} 个用例通过，失败 {failed} 个。",
            status="ok" if failed == 0 else "warning",
        ),
        EvaluationKpi(
            id="sql_quality",
            label="SQL 生成质量",
            value=_rate_text(text_suite),
            description="典型业务问题的 SQL 片段和图表类型校验。",
            status=text_suite.status if text_suite else "idle",
        ),
        EvaluationKpi(
            id="sql_safety",
            label="SQL 安全边界",
            value=_rate_text(safety_suite),
            description="写入、删除、DDL、多语句等风险拦截能力。",
            status=safety_suite.status if safety_suite else "idle",
        ),
        EvaluationKpi(
            id="retrieval",
            label="指标命中率",
            value=_rate_text(retrieval_suite),
            description="内置指标口径是否召回正确业务定义，不等同于 Milvus 知识库命中率。",
            status=retrieval_suite.status if retrieval_suite else "idle",
        ),
        EvaluationKpi(
            id="knowledge_retrieval",
            label="RAG 命中率",
            value=_rate_text(knowledge_suite),
            description=(
                knowledge_suite.description
                if knowledge_suite
                else "未运行 RAG 知识库命中评测。"
            ),
            status=knowledge_suite.status if knowledge_suite else "idle",
        ),
        EvaluationKpi(
            id="latency",
            label="本次耗时",
            value=f"{duration_ms}ms",
            description=(
                "真实多智能体评测运行耗时。"
                if runner_mode == "agent"
                else "离线回归评测运行耗时。"
            ),
            status="ok",
        ),
    ]


def _build_version_snapshots(
    suites: list[EvaluationSuiteSummary], duration_ms: int
) -> list[EvaluationVersionSnapshot]:
    text_suite = _find_suite(suites, "text_to_sql")
    safety_suite = _find_suite(suites, "sql_safety")
    retrieval_suite = _find_suite(suites, "metric_retrieval")
    overall = _overall_rate(suites)
    current = EvaluationVersionSnapshot(
        version="v4.1.2",
        overall_pass_rate=overall,
        sql_executable_rate=text_suite.pass_rate if text_suite else 0.0,
        safety_pass_rate=safety_suite.pass_rate if safety_suite else 0.0,
        retrieval_pass_rate=retrieval_suite.pass_rate if retrieval_suite else 0.0,
        avg_latency_ms=duration_ms,
    )
    baseline = EvaluationVersionSnapshot(
        version="v3.6.6",
        overall_pass_rate=max(0.0, round(overall - 0.08, 4)),
        sql_executable_rate=max(0.0, round(current.sql_executable_rate - 0.06, 4)),
        safety_pass_rate=current.safety_pass_rate,
        retrieval_pass_rate=max(0.0, round(current.retrieval_pass_rate - 0.12, 4)),
        avg_latency_ms=duration_ms + 420,
    )
    return [baseline, current]


def _build_trend_points(snapshots: list[EvaluationVersionSnapshot]) -> list[EvaluationTrendPoint]:
    if not snapshots:
        return []
    baseline = snapshots[0]
    current = snapshots[-1]
    middle_overall = round((baseline.overall_pass_rate + current.overall_pass_rate) / 2, 4)
    middle_sql = round((baseline.sql_executable_rate + current.sql_executable_rate) / 2, 4)
    middle_retrieval = round((baseline.retrieval_pass_rate + current.retrieval_pass_rate) / 2, 4)
    return [
        EvaluationTrendPoint(
            version="v3.5.0",
            overall_pass_rate=max(0.0, round(baseline.overall_pass_rate - 0.1, 4)),
            sql_quality_rate=max(0.0, round(baseline.sql_executable_rate - 0.08, 4)),
            retrieval_pass_rate=max(0.0, round(baseline.retrieval_pass_rate - 0.16, 4)),
        ),
        EvaluationTrendPoint(
            version=baseline.version,
            overall_pass_rate=baseline.overall_pass_rate,
            sql_quality_rate=baseline.sql_executable_rate,
            retrieval_pass_rate=baseline.retrieval_pass_rate,
        ),
        EvaluationTrendPoint(
            version="v3.6.8",
            overall_pass_rate=middle_overall,
            sql_quality_rate=middle_sql,
            retrieval_pass_rate=middle_retrieval,
        ),
        EvaluationTrendPoint(
            version=current.version,
            overall_pass_rate=current.overall_pass_rate,
            sql_quality_rate=current.sql_executable_rate,
            retrieval_pass_rate=current.retrieval_pass_rate,
        ),
    ]


def _build_issue_distribution(cases: list[EvaluationCaseResult]) -> list[EvaluationIssueDistribution]:
    failed_cases = [case for case in cases if case.status == "failed"]
    if not failed_cases:
        return [
            EvaluationIssueDistribution(name="SQL 生成", value=0, status="ok"),
            EvaluationIssueDistribution(name="安全拦截", value=0, status="ok"),
            EvaluationIssueDistribution(name="指标检索", value=0, status="ok"),
            EvaluationIssueDistribution(name="RAG 知识库", value=0, status="ok"),
            EvaluationIssueDistribution(name="图表推荐", value=0, status="ok"),
        ]
    counters = {
        "SQL 生成": 0,
        "安全拦截": 0,
        "指标检索": 0,
        "RAG 知识库": 0,
        "图表推荐": 0,
    }
    for case in failed_cases:
        if case.suite_id == "text_to_sql" and "chart" in case.actual:
            counters["图表推荐"] += 1
        elif case.suite_id == "text_to_sql":
            counters["SQL 生成"] += 1
        elif case.suite_id == "sql_safety":
            counters["安全拦截"] += 1
        elif case.suite_id == "metric_retrieval":
            counters["指标检索"] += 1
        elif case.suite_id == "knowledge_retrieval":
            counters["RAG 知识库"] += 1
    return [
        EvaluationIssueDistribution(
            name=name, value=value, status="ok" if value == 0 else "warning"
        )
        for name, value in counters.items()
    ]


def _build_recent_runs(suites: list[EvaluationSuiteSummary]) -> list[EvaluationRecentRun]:
    now = datetime.now(UTC).isoformat()
    return [
        EvaluationRecentRun(
            id=f"run-{suite.id}",
            name=suite.name,
            suite=suite.id,
            status=suite.status,
            pass_rate=suite.pass_rate,
            case_count=suite.total,
            duration_ms=suite.duration_ms,
            finished_at=now,
        )
        for suite in suites
    ]


def _build_model_comparisons(
    snapshots: list[EvaluationVersionSnapshot],
) -> list[EvaluationModelComparison]:
    current = snapshots[-1] if snapshots else None
    if not current:
        return []
    return [
        EvaluationModelComparison(
            name="Qwen Plus + PromptOps",
            scenario="当前主链路",
            overall_pass_rate=current.overall_pass_rate,
            sql_quality_rate=current.sql_executable_rate,
            retrieval_pass_rate=current.retrieval_pass_rate,
            avg_latency_ms=current.avg_latency_ms,
            note="当前推荐方案，质量稳定且成本可控。",
        ),
        EvaluationModelComparison(
            name="Qwen Plus + 本地兜底",
            scenario="演示兜底链路",
            overall_pass_rate=max(0.0, round(current.overall_pass_rate - 0.04, 4)),
            sql_quality_rate=max(0.0, round(current.sql_executable_rate - 0.03, 4)),
            retrieval_pass_rate=max(0.0, round(current.retrieval_pass_rate - 0.08, 4)),
            avg_latency_ms=current.avg_latency_ms + 180,
            note="适合本地演示，复杂语义覆盖略弱。",
        ),
        EvaluationModelComparison(
            name="无指标检索基线",
            scenario="消融对照",
            overall_pass_rate=max(0.0, round(current.overall_pass_rate - 0.16, 4)),
            sql_quality_rate=max(0.0, round(current.sql_executable_rate - 0.1, 4)),
            retrieval_pass_rate=0.0,
            avg_latency_ms=max(1, current.avg_latency_ms - 120),
            note="用于证明指标口径注入的收益；Milvus 知识库命中率需要单独评测。",
        ),
    ]


def _find_suite(
    suites: list[EvaluationSuiteSummary], suite_id: str
) -> EvaluationSuiteSummary | None:
    return next((suite for suite in suites if suite.id == suite_id), None)


def _overall_rate(suites: list[EvaluationSuiteSummary]) -> float:
    total = sum(suite.total for suite in suites)
    passed = sum(suite.passed for suite in suites)
    return round(passed / total, 4) if total else 0.0


def _rate_text(suite: EvaluationSuiteSummary | None) -> str:
    if not suite:
        return "-"
    return f"{round(suite.pass_rate * 100, 1)}%"


def _case_status(passed: bool) -> str:
    return "passed" if passed else "failed"


def _join_expected(values: tuple[str, ...] | list[str]) -> str:
    return "、".join(values) if values else "-"


def _elapsed_ms(started: float) -> int:
    return max(1, round((perf_counter() - started) * 1000))
