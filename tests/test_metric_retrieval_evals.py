from app.evals.metric_retrieval import (
    load_metric_retrieval_cases,
    run_metric_retrieval_evals,
)


def test_load_metric_retrieval_cases() -> None:
    cases = load_metric_retrieval_cases()

    assert len(cases) >= 5
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.question for case in cases)
    assert all(case.expected_metrics for case in cases)


def test_metric_retrieval_eval_report_passes_current_baseline() -> None:
    report = run_metric_retrieval_evals()

    assert report.total >= 5
    assert report.failed == 0
    assert report.pass_rate == 1.0
    assert all(result.passed for result in report.results)


def test_metric_retrieval_eval_report_is_serializable() -> None:
    report = run_metric_retrieval_evals()
    payload = report.to_dict()

    assert payload["total"] == report.total
    assert payload["passed"] == report.passed
    assert payload["failed"] == 0
    assert payload["pass_rate"] == 1.0
    assert len(payload["results"]) == report.total
