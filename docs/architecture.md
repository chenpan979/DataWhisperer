# DataWhisperer 架构说明

这份文档用于解释 DataWhisperer v1 的核心架构。它适合放在 GitHub，也适合面试前复习。

## 一句话架构

DataWhisperer v1 是一个单主控 Agent 工作流：

```text
用户问题 -> 读取 Schema -> 生成 SQL -> 安全校验 -> 执行查询 -> 推荐图表 -> 生成分析结论 -> 返回统一响应
```

## 模块职责

### API 层：`app/api`

API 层只做三件事：

- 接收 HTTP 请求。
- 调用业务编排层。
- 返回标准化响应。

这样做的好处是接口代码不会和大模型、数据库、图表逻辑混在一起，后续改前端或者加更多接口时更清楚。

### 主控层：`app/agent/orchestrator.py`

`DataAnalysisOrchestrator` 是整个流程的调度中心。

它本身不负责具体能力，而是按顺序调用不同工具：

- `schema_tool` 获取数据库结构。
- `sql_tool` 生成并校验 SQL。
- `query_tool` 执行查询。
- `chart_tool` 推荐图表。
- `insight_tool` 生成业务分析。

这种写法接近真实 Agent 工程里的工具编排思路，也方便后续升级为 MCP 或多智能体。

### Core 层：`app/core`

Core 层放基础设施：

- `config.py`：读取 `.env` 配置。
- `database.py`：创建数据库连接和 session。
- `llm.py`：封装 OpenAI-compatible 大模型接口。

这样做是为了把“项目运行依赖”集中管理，避免配置散落在各个业务文件里。

### Tools 层：`app/tools`

Tools 层是 v1 的核心能力集合。

| 文件 | 职责 |
| --- | --- |
| `schema_tool.py` | 读取 MySQL 表结构，并压缩成适合 prompt 的文本 |
| `sql_tool.py` | 调用大模型生成 SQL，并做只读安全校验 |
| `query_tool.py` | 执行已经通过校验的 SQL |
| `chart_tool.py` | 根据查询结果推荐 ECharts 图表配置 |
| `insight_tool.py` | 根据查询结果生成中文业务结论 |

## 为什么不直接让大模型执行所有事情？

因为大模型适合做语言理解和候选方案生成，但不适合直接承担安全边界。

所以 DataWhisperer 的设计是：

- 大模型负责理解问题、生成候选 SQL、总结结果。
- 服务端代码负责校验 SQL、限制查询、执行数据库访问。
- 工具层负责把每个能力拆成可测试、可替换的模块。

这也是项目里最重要的工程点。

## SQL 安全边界

`sql_tool.py` 会在服务端做安全校验：

- 只允许 `SELECT` / `WITH` 开头的只读查询。
- 禁止多语句。
- 禁止 SQL 注释。
- 禁止 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER`、`TRUNCATE` 等危险语句。
- 自动补充 `LIMIT`。

即使 prompt 里要求模型“不要生成危险 SQL”，服务端仍然要校验。因为 prompt 不是安全边界。

## 为什么要返回 trace？

`trace_steps` 用来记录每一步执行情况，例如：

- 是否读取了 schema。
- 是否生成了 SQL。
- SQL 是否通过安全校验。
- 查询返回了多少行。
- 生成了什么图表类型。

这对开发调试和面试讲解都很有帮助。面试官看到 trace，会更容易理解你不是只调用了一个模型接口，而是在做完整的工程闭环。

## 后续如何扩展 MCP？

当前 Tools 层已经具备 MCP 化的雏形。

后续可以把这些函数包装成 MCP 工具：

- `get_schema_overview`
- `generate_safe_sql`
- `execute_query`
- `build_chart_spec`
- `summarize_insight`

到那时，主控 Agent 不再直接 import Python 函数，而是通过 MCP 协议调用工具。

## 后续如何扩展多智能体？

可以把当前单主控流程拆成多个角色：

- Schema Analyst：理解表结构和字段含义。
- SQL Engineer：生成 SQL。
- Safety Reviewer：审查 SQL 风险。
- Chart Designer：选择图表。
- Report Writer：生成业务分析。

v1 先不这样做，是因为第一阶段最重要的是跑通闭环。多智能体应该建立在稳定工具和清晰接口之上，而不是一开始就增加复杂度。
