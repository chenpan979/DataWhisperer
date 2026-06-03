from app.rag.metric_retriever import MetricRetriever, get_metric_retriever


def test_metric_retriever_finds_gmv_definition() -> None:
    result = get_metric_retriever().retrieve("最近 6 个月 GMV 趋势")

    assert result.names[0] == "GMV"
    assert result.retrieval_mode == "hybrid_lexical_ngram_v1"
    assert result.metrics[0].score > 0
    assert "SUM(order_items.quantity * order_items.unit_price)" in result.prompt_context


def test_metric_retriever_finds_avg_order_value_definition() -> None:
    result = get_metric_retriever().retrieve("哪个地区客单价最高")

    assert "客单价" in result.names
    assert "COUNT(DISTINCT orders.order_id)" in result.prompt_context


def test_metric_retriever_uses_semantic_overlap_for_related_expression() -> None:
    result = get_metric_retriever().retrieve("比较不同地区平均每单消费水平", min_score=0.2)

    assert "客单价" in result.names
    assert "hybrid_lexical_ngram_v1" in result.prompt_context


def test_metric_retriever_finds_repurchase_rate_definition() -> None:
    result = get_metric_retriever().retrieve("复购率最高的客户行业")

    assert "复购率" in result.names
    assert "repurchase_rate_percent" in result.prompt_context


def test_metric_retriever_returns_empty_context_when_no_match(tmp_path) -> None:
    retriever = MetricRetriever(knowledge_dir=tmp_path)

    result = retriever.retrieve("随便问一个没有指标的问题")

    assert result.names == []
    assert result.prompt_context == "未检索到相关业务指标口径。"
