from app.models.conversations import ConversationTurn


def test_conversation_turn_keeps_assistant_html_snapshot() -> None:
    """历史会话需要保存回答卡片 HTML，避免重启后丢失图表、下拉和追问样式。"""

    turn = ConversationTurn(
        traceId="trace-html-snapshot",
        question="查询各商品品类销售额占比",
        insight="电子产品品类销售额最高。",
        createdAt="17:42",
        assistantHtml='<article class="chat-message assistant">snapshot</article>',
    )

    assert "chat-message assistant" in turn.assistantHtml
