from app.api.examples import EXAMPLE_QUESTIONS


def test_examples_include_region_order_count() -> None:
    questions = [example.question for example in EXAMPLE_QUESTIONS]

    assert "\u67e5\u8be2\u5404\u5730\u533a\u8ba2\u5355\u6570\u91cf" in questions


def test_examples_have_required_demo_metadata() -> None:
    for example in EXAMPLE_QUESTIONS:
        assert example.question
        assert example.intent
        assert example.expected_chart in {"bar", "line", "pie", "table"}
        assert example.notes
