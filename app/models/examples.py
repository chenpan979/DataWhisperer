from pydantic import BaseModel, Field


class ExampleQuestion(BaseModel):
    """前端和 Swagger 中展示的示例问题。

    示例问题的作用是降低首次体验成本：用户不需要先理解示例库表结构，
    就能直接点击问题，看到 SQL、图表和分析结果。
    """

    question: str = Field(description="Natural-language question to send to /api/chat/query.")
    intent: str = Field(description="What business analysis this example demonstrates.")
    expected_chart: str = Field(description="Likely chart type returned by the chart tool.")
    notes: str = Field(description="Short explanation for learners and demo users.")


class ExamplesResponse(BaseModel):
    """示例问题列表的接口响应模型。"""

    examples: list[ExampleQuestion]
