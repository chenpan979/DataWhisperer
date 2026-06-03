# DataWhisperer V3 RAG 指标口径库设计说明

## 版本目标

V3 的目标是让 DataWhisperer 不只理解数据库 schema，还能理解业务指标口径。

V1 解决的是 Text-to-SQL 闭环能不能跑通。

V2 解决的是 prompt 能不能治理、SQL 失败能不能修复、能力有没有基础评测。

V3 开始补业务知识：

```text
用户问题 -> 检索指标口径 -> 注入 SQL prompt -> 生成更符合业务定义的 SQL
```

## 为什么需要指标口径库？

真实业务问题经常不会直接说表名和字段名，而是会说：

- GMV
- 销售额
- 客单价
- 订单数
- 复购率

这些词在数据库里不一定有同名字段。模型只看 schema 时，可能不知道这些指标应该怎么算。

所以 V3 新增 `knowledge/metrics/`，把业务指标定义成可检索的知识库。

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

`app/rag/metric_retriever.py` 新增 `MetricRetriever`。

当前 V3.0 使用轻量关键词检索：

- 指标名称命中加权最高。
- 别名命中加权较高。
- 关键词命中作为补充。
- 返回 top 3 个相关指标。

这不是最终形态，但它已经能跑通 RAG 的核心流程。

后续可以把 `retrieve()` 升级成 embedding 检索，而不需要改主控流程。

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

## 当前限制

V3.0 先不接向量数据库，原因是：

- 本地指标库更容易理解和维护。
- 不需要额外部署 Chroma、FAISS、Milvus。
- 先验证 RAG 是否真的能提升 Text-to-SQL 的业务理解。
- 后续升级 embedding 检索时，主控流程不用大改。

## 下一步

V3.1 可以升级 embedding 检索：

```text
用户问题 -> embedding -> 向量相似度 -> 指标口径 -> prompt 注入 -> SQL 生成
```

V3.2 可以增加指标口径评测集：

- 问题是否命中正确指标。
- SQL 是否使用正确计算公式。
- 指标定义冲突时是否能给出提醒。
- 不存在指标时是否能明确说明。
