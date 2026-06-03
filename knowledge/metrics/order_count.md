# 订单数

aliases: 订单数, 订单数量, 下单数, 订单量
keywords: 订单, 订单数, 订单数量, 下单, order count
tables: orders, regions, customers
fields: orders.order_id, orders.region_id, orders.customer_id

## 业务含义

订单数表示满足条件的订单数量，常用于衡量地区、客户或时间维度上的交易活跃度。

## 计算口径

在当前示例库中，订单数应使用订单主表的订单 ID 去重统计：

```sql
COUNT(DISTINCT orders.order_id)
```

## SQL 建议

- 按地区统计订单数时，连接 `orders` 和 `regions`。
- 按客户行业统计订单数时，连接 `orders` 和 `customers`。
- 建议别名使用 `order_count`。

## 注意事项

如果查询连接了 `order_items`，必须使用 `COUNT(DISTINCT orders.order_id)`，避免订单明细导致重复计数。
