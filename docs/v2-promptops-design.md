# DataWhisperer V2 PromptOps 设计说明

## 版本目标

V2 的目标是把 DataWhisperer 从“能跑通的 Text-to-SQL MVP”升级成“提示词可治理、SQL 可自修复、链路可追踪”的大模型数据分析应用。

本阶段已经完成：

- 将 SQL 生成、SQL 修复、分析总结、图表推荐 prompt 从代码中拆出。
- 通过目录结构管理 `prompt_id` 和 `version`。
- 每次请求返回实际使用的 prompt 版本。
- SQL 校验失败或数据库执行失败时，最多自动修复 1 次。
- 通过 `repair_count` 记录本次请求的 SQL 修复次数。
- 增加基础 Text-to-SQL 评测集，用固定问题检查基础能力是否退化。

## 目录结构

```text
prompts/
  sql_generation/
    v1/
      system.md
      user.md
  sql_repair/
    v1/
      system.md
      user.md
  insight_summary/
    v1/
      system.md
      user.md
  chart_recommendation/
    v1/
      system.md
      user.md
```

说明：

- `sql_generation`：负责自然语言问题转 SQL。
- `sql_repair`：负责在 SQL 校验失败或数据库执行失败后修复 SQL。
- `insight_summary`：负责基于查询结果生成业务结论。
- `chart_recommendation`：当前先作为预留模板，图表推荐仍使用稳定规则。
- `v1`：代表模板版本，后续可以新增 `v2`、`v3`，用于 A/B 测试或回滚。

## PromptRegistry

`app/core/prompts.py` 新增 `PromptRegistry`，职责包括：

- 根据 `prompt_id/version/role` 读取模板。
- 解析模板变量，例如 `{question}`、`{schema_prompt}`。
- 渲染 Chat Completions messages。
- 返回 `PromptRenderResult`，记录 prompt_id、version、messages、变量和模板路径。

这样业务代码不需要关心 prompt 文件在哪里，只需要调用：

```python
rendered = registry.render_messages(
    "sql_generation",
    version="v1",
    variables={
        "schema_prompt": schema_prompt,
        "question": question,
    },
)
```

## SQL 自修复流程

V2 已接入 SQL 失败自修复：

```text
生成 SQL
  -> 安全校验失败或数据库执行失败
  -> 记录失败原因
  -> 调用 sql_repair@v1
  -> 重新生成 SQL
  -> 再次执行安全校验和查询
  -> 最多修复 1 次
```

需要强调的是：修复后的 SQL 不会直接执行，仍然必须再次经过服务端安全校验。

这保证了一个原则：

> 模型可以参与修复，但安全边界仍然在服务端代码里。

## API 响应增强

`POST /api/chat/query` 响应新增：

```json
{
  "prompt_versions": {
    "sql_generation": "v1",
    "sql_repair": "v1",
    "insight_summary": "v1"
  },
  "repair_count": 1
}
```

字段说明：

- `prompt_versions`：记录本次请求实际使用过的 prompt 版本。
- `repair_count`：记录 SQL 自动修复次数。当前最多为 1。

## 基础评测集

V2 新增 `evals/text_to_sql_cases.json`，用于维护固定评测问题。

每个评测用例包含：

- `id`：用例唯一标识。
- `question`：自然语言问题。
- `tags`：问题标签，例如 sales、trend、bar。
- `expected_sql_contains`：期望 SQL 包含的关键片段。
- `forbidden_sql_contains`：SQL 中禁止出现的危险片段。
- `expected_columns`：期望结果字段。
- `expected_chart_type`：期望图表类型。
- `must_be_safe`：是否必须通过 SQL 安全校验。

当前 runner 位于 `app/evals/text_to_sql.py`，先采用轻量离线规则：

- 不启动数据库。
- 不调用真实大模型。
- 使用项目内置 fallback SQL 作为基线。
- 检查 SQL 安全、SQL 关键片段和图表类型。

这样做的好处是测试速度快，适合作为基础质量门禁。

## 为什么这样设计？

### 1. 改 prompt 不应该改业务代码

V1 里 prompt 写在 Python 文件里，后续调 prompt 时容易影响业务代码。

V2 拆成模板文件后，调优 prompt 更像配置变更，工程边界更清楚。

### 2. 每次模型输出都应该可追踪

如果某次 SQL 生成效果变差，需要知道它使用了哪个 prompt 版本。

`prompt_versions` 可以帮助定位问题，也方便后续做回滚和评测。

### 3. SQL 失败不应该直接终止

真实 Text-to-SQL 场景里，模型可能写错字段名、表名或 SQL 语法。

如果系统一错就失败，用户体验会比较差。

V2 增加自修复后，系统可以把错误信息反馈给模型，让模型基于错误原因修正 SQL。

### 4. 后续评测需要版本信息

Text-to-SQL 不能只靠“感觉好像能用”，应该通过固定评测集比较不同 prompt 版本。

有了 prompt_id 和 version，后面就可以记录：

- 哪个版本 SQL 正确率更高。
- 哪个版本安全校验失败更少。
- 哪个版本分析结论更稳定。
- 哪个版本修复成功率更高。

## 下一步

下一步建议把评测能力升级成命令行工具，例如：

```powershell
python -m app.evals.text_to_sql
```

并输出 JSON 报告或 Markdown 报告。

再往后可以接入真实 LLM 评测，对比不同 prompt 版本的 SQL 生成质量。
