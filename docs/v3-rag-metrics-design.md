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

### V3.3：Milvus 向量数据库检索层

新增 Milvus standalone 部署配置、指标向量化器、Milvus 指标索引同步脚本和可回退检索器。

V3.3 的核心思想是：

- `knowledge/metrics/*.md` 仍然是指标口径知识源。
- Milvus 只作为可重建的向量索引层。
- 默认仍然使用本地 hybrid 检索，保证项目开箱可跑。
- 当 `METRIC_RETRIEVAL_PROVIDER=milvus` 时，优先走 Milvus 向量检索。
- 当 Milvus 不可用且 `MILVUS_AUTO_FALLBACK=true` 时，自动回退到本地 hybrid 检索。

### V3.4：DashScope Embedding 语义向量化

V3.4 将指标向量化从本地 hashing 升级为 DashScope `text-embedding-v4`。

核心变化：

- 使用 `DASHSCOPE_API_KEY` 调用 OpenAI-compatible embeddings 接口。
- 默认 embedding 模型为 `text-embedding-v4`。
- 默认指标向量维度为 1024。
- Milvus collection 的维度和 embedding 输出维度保持一致。
- 没有配置 DashScope Key 时，可以通过 `EMBEDDING_AUTO_FALLBACK=true` 回退到本地 hashing。

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

V3.3/V3.4 接入 Milvus 后，检索模式可能为：

```text
milvus_vector_v1
```

如果 Milvus 不可用并触发兜底，检索模式仍会回到：

```text
hybrid_lexical_ngram_v1
```

## Milvus 索引同步

V3.3/V3.4 相关文件：

```text
app/rag/embeddings.py
app/rag/milvus_metric_store.py
app/rag/milvus_metric_retriever.py
app/rag/milvus_sync.py
```

同步流程：

```text
读取 knowledge/metrics/*.md
  -> 使用 DashScope text-embedding-v4 生成固定维度向量
  -> 重建 Milvus collection
  -> 写入指标名称、别名、关键词、正文和向量
```

运行方式：

```powershell
pip install -e ".[milvus]"
docker-compose up -d etcd minio milvus
python -m app.rag.milvus_sync
```

V3.4 推荐环境变量：

```env
DASHSCOPE_API_KEY=你的 DashScope API Key
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
DASHSCOPE_EMBEDDING_DIMENSION=1024
EMBEDDING_PROVIDER=dashscope
METRIC_RETRIEVAL_PROVIDER=milvus
```

本地 hashing 向量化器仍然保留，原因是：

- 没有 API Key 时，项目仍然可以跑基础测试和演示。
- Milvus 或 embedding 服务不可用时，系统可以回退到本地检索。
- 后续替换成其他 embedding 模型时，只需要替换向量化器工厂，不需要改主控流程。

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

V3.4 已经接入 DashScope Embedding 和 Milvus，但仍然有几个刻意保留的工程边界：

- Milvus 指标索引采用全量重建，适合小规模指标库和演示，后续可升级为增量 upsert。
- Milvus 检索只用于业务指标口径，暂未扩展到报表样例、SQL 案例库或企业数据字典。
- 当前没有缓存远程 embedding 调用结果，后续可按指标文件 hash 做缓存和增量同步。
- 本地 hybrid 检索仍然保留，作为 Milvus 不可用时的稳定兜底。

## 下一步

V3.5 或 V4 前可以继续增强：

- 增加指标索引增量同步和索引版本号。
- 增加 embedding 缓存，避免重复调用远程模型。
- 增加指标冲突检测。
- 增加“未命中指标”的用户提示。
- 将指标检索工具包装成 MCP 工具。
