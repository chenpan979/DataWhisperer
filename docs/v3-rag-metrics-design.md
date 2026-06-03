# DataWhisperer V3 RAG 指标口径库设计说明

## 版本目标

V3 的目标是让 DataWhisperer 不只理解数据库 schema，还能理解业务指标口径。

V1 解决的是 Text-to-SQL 闭环能不能跑通。

V2 解决的是 prompt 能不能治理、SQL 失败能不能修复、能力有没有基础评测。

V3 开始补业务知识：

```text
用户问题 -> 检索指标口径 -> 注入 SQL prompt -> 生成更符合业务定义的 SQL
```

## 版本拆分

### V3.0：本地指标口径库

新增 `knowledge/metrics/`，维护 GMV、销售额、客单价、订单数、复购率等业务指标定义。

### V3.1：混合指标检索

检索策略从纯关键词升级为 hybrid retrieval：

- 关键词/别名精确匹配：保证强业务词稳定命中。
- 本地 n-gram 相似度：补充“平均每单消费水平”这类非完全关键词表达。

当前不依赖外部向量数据库，后续可以把语义相似度部分替换成 embedding。

### V3.2：指标检索评测集

新增 `evals/metric_retrieval_cases.json`，用于评估：

- 问题是否命中正确指标。
- 是否误召回禁止指标。
- 检索报告是否可序列化。
- 混合检索是否覆盖同义表达。

## 指标库目录

```text
knowledge/
  metrics/
    gmv.md
    sales_amount.md
    avg_order_value.md
    order_count.md
    repurchase_rate.md
```

每个指标文件包含：

- 指标名称
- 别名
- 关键词
- 相关表
- 相关字段
- 业务含义
- 计算口径
- SQL 建议
- 注意事项

## 检索工具

`app/rag/metric_retriever.py` 提供 `MetricRetriever`。

当前检索流程：

```text
读取本地指标库
  -> 计算关键词/别名得分
  -> 计算 n-gram 语义相似度
  -> 合并分数
  -> 返回 top-k 指标
  -> 压缩成 prompt_context
```

检索结果会包含：

- 指标名称
- 匹配词
- lexical_score
- semantic_score
- 综合 score
- retrieval_mode

当前检索模式为：

```text
hybrid_lexical_ngram_v1
```

## Prompt 注入

SQL 生成 prompt 从：

```text
数据库结构 + 用户问题
```

升级成：

```text
数据库结构 + 相关业务指标口径 + 用户问题
```

SQL 修复 prompt 也同步注入指标口径，避免修复时丢失业务定义。

## API 响应增强

`POST /api/chat/query` 响应新增：

```json
{
  "retrieved_metrics": ["GMV", "销售额"]
}
```

这个字段可以帮助前端或调试工具展示：本次问题到底参考了哪些业务指标定义。

## 评测集

V3.2 新增：

```text
evals/metric_retrieval_cases.json
app/evals/metric_retrieval.py
```

运行方式：

```powershell
python -m app.evals.metric_retrieval
```

报告示例：

```json
{
  "total": 5,
  "passed": 5,
  "failed": 0,
  "pass_rate": 1.0
}
```

## 当前限制

V3.1 仍然不接外部向量数据库，原因是：

- 本地指标库更容易理解和维护。
- 不需要额外部署 Chroma、FAISS、Milvus。
- 先验证 RAG 是否真的能提升 Text-to-SQL 的业务理解。
- 后续升级 embedding 检索时，主控流程不用大改。

## 下一步

V3.3 或 V4 前可以继续增强：

- 使用真实 embedding 模型替换 n-gram 相似度。
- 增加指标冲突检测。
- 增加“未命中指标”的用户提示。
- 将指标检索工具包装成 MCP 工具。
