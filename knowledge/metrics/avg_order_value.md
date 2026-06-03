# 客单价

aliases: 客单价, 平均订单金额, AOV, average order value
keywords: 客单价, 平均订单, 订单均价, aov, avg order
tables: orders, order_items, regions
fields: orders.order_id, orders.region_id, order_items.quantity, order_items.unit_price

## 业务含义

客单价表示平均每个订单带来的销售金额，常用于比较不同地区或不同客户群体的消费水平。

## 计算口径

在当前示例库中，客单价计算方式为：

```sql
SUM(order_items.quantity * order_items.unit_price) / COUNT(DISTINCT orders.order_id)
```

## SQL 建议

- 按地区分析客单价时，连接 `orders`、`order_items`、`regions`。
- 分组字段可以使用 `regions.region_name`。
- 建议别名使用 `avg_order_value`。

## 注意事项

分母必须使用 `COUNT(DISTINCT orders.order_id)`，避免一个订单多条明细导致订单数被重复计算。
