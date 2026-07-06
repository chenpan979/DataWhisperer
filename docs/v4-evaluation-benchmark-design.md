# V4 评测体系与大样本 Benchmark 设计

DataWhisperer 后续要证明的不只是“能生成 SQL”，而是：在不同 SQL 难度、不同业务知识依赖、不同 Agent 组合下，系统质量是否稳定提升。

## 1. 样例数据库规模

`scripts/mysql_sample.sql` 已从早期演示数据升级为更接近真实企业库的电商经营分析样例库。

核心规模：

- 6 个地区。
- 5 类客户分层。
- 500 个客户，覆盖零售、科技、食品、贸易、金融、制造、教育、医疗等行业。
- 16 个品类节点，包含父子品类关系。
- 8 个供应商。
- 8 个仓库。
- 30 个商品。
- 6 个销售渠道。
- 8 个营销活动。
- 6 类优惠券。
- 5000 笔订单。
- 8000 条以上订单明细。
- 3000 条以上库存快照。
- 支付、物流、退货、评价、客服工单等经营链路数据。

## 2. 表结构复杂度

当前样例库从 5 张表扩展为 18 张表：

| 模块 | 表 | 说明 |
| --- | --- | --- |
| 地区与客户 | regions、customer_segments、customers | 地区、客户行业、客户分层 |
| 商品中心 | categories、suppliers、products | 父子品类、供应商、商品主数据 |
| 履约库存 | warehouses、inventory_snapshots | 仓库与库存快照 |
| 营销渠道 | sales_channels、campaigns、coupons | 渠道、活动、优惠券 |
| 交易核心 | orders、order_items、payments、shipments | 订单、明细、支付、物流 |
| 售后体验 | returns、product_reviews、support_tickets | 退货、评价、客服工单 |

保留兼容字段：

- `products.category` 仍然保留，兼容现有 Text-to-SQL 和图表逻辑。
- `orders.region_id / customer_id / order_date / status` 仍然保留。
- `order_items.product_id / quantity / unit_price` 仍然保留。

因此旧问题仍能跑，新问题可以逐步扩展到：渠道 ROI、活动效果、供应商交付、库存周转、退货率、评价情绪、客服响应等更复杂场景。

## 3. 测试集分层

默认内置集：`evals/text_to_sql_cases.json`

- 60 条稳定回归用例。
- 用于每次开发后快速验证。
- 保证当前 fallback / prompt 链路能稳定通过。

真实 Agent 核心集：`evals/text_to_sql_18_table_cases.jsonl`

- 18 条核心用例，每类问题至少覆盖一张关键业务表。
- 默认供 `runner_mode=agent` 调用真实多智能体链路，验证 Schema Linking、Knowledge Retrieval、Query Planning、SQL Generation、Validation、Chart 和 Insight 的端到端效果。

上传演示集：`evals/text_to_sql_upload_100_cases.jsonl`

- 100 条 JSONL，可在“测试集管理”页面上传。
- 用于演示自定义测试集如何进入评测中心。

产品级大评测集：`evals/text_to_sql_product_240_cases.jsonl` / `evals/text_to_sql_product_360_cases.jsonl`

- 240 / 360 条用例，覆盖 18 张业务表和 simple / medium / complex 三档难度。
- 适合上传到“测试集管理”，再到“评测中心”运行。
- 用于版本发布前、CSDN 展示、面试讲解和后续 RAG、SQL 修复、多智能体消融实验。

生成脚本：`scripts/regenerate_eval_datasets.py`

- 所有 Text-to-SQL 评测集统一由脚本生成，避免手工维护导致乱码、重复或覆盖不完整。

难度分布：

| 难度 | 占比 | 典型能力 |
| --- | --- | --- |
| simple | 40% | 单表/简单 Join、分组统计、排序 |
| medium | 40% | 多表 Join、聚合、时间趋势、占比、客单价 |
| complex | 20% | CTE、环比、TopN、销售下滑、跨周期比较 |

## 4. 消融实验规划

| 实验版本 | RAG | SQL-of-Thought | SQL 修复 | 多 Agent | 目的 |
| --- | --- | --- | --- | --- | --- |
| Baseline | 否 | 否 | 否 | 否 | 看基础 Text-to-SQL 能力 |
| + RAG | 是 | 否 | 否 | 否 | 证明指标口径检索的收益 |
| + SQL-of-Thought | 是 | 是 | 否 | 是 | 证明查询规划和 schema linking 的收益 |
| + SQL Repair | 是 | 是 | 是 | 是 | 证明错误诊断和修复 Agent 的收益 |
| Full Agent | 是 | 是 | 是 | 是 | 当前完整链路效果 |

## 5. 下一步

- 前端评测中心展示 simple / medium / complex 准确率。
- 增加有 RAG / 无 RAG 的同集对比。
- 增加 SQL-of-Thought 与 SQLRepairAgent 的消融开关。
- 把评测结果落库，形成版本趋势和失败案例库。
- 在大样例库基础上继续扩展渠道、库存、售后、客服类复杂 SQL 测试集。
