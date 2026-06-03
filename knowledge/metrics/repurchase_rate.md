# 复购率

aliases: 复购率, 重复购买率, 回购率, repeat purchase rate
keywords: 复购, 复购率, 重复购买, 回购, repeat purchase
tables: orders, customers
fields: orders.order_id, orders.customer_id, customers.customer_id, customers.industry

## 业务含义

复购率表示有多次下单行为的客户占全部下单客户的比例，用于衡量客户持续购买能力。

## 计算口径

在当前示例库中，可以先按客户统计订单数，再计算订单数大于等于 2 的客户占比：

```sql
COUNT(CASE WHEN order_count >= 2 THEN 1 END) / COUNT(*) * 100
```

通常需要先构造客户订单数子查询：

```sql
SELECT customer_id, COUNT(DISTINCT order_id) AS order_count
FROM orders
GROUP BY customer_id
```

## SQL 建议

- 先按 `orders.customer_id` 聚合订单数。
- 再统计订单数大于等于 2 的客户比例。
- 如果按行业分析，需要连接 `customers` 表并按 `customers.industry` 分组。
- 建议别名使用 `repurchase_rate_percent`。

## 注意事项

当前示例库订单量较小，复购率仅用于演示指标口径，不代表真实生产数据分布。
