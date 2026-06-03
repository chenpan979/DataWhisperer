# 销售额

aliases: 销售额, 销售金额, 营收, 收入
keywords: 销售, 销售额, 销售金额, 营收, 收入, amount
tables: orders, order_items
fields: orders.order_id, orders.order_date, order_items.quantity, order_items.unit_price

## 业务含义

销售额表示订单商品明细产生的销售金额，适合用于分析地区、品类、商品或月份的销售表现。

## 计算口径

在当前示例库中，销售额按订单明细计算：

```sql
SUM(order_items.quantity * order_items.unit_price)
```

## SQL 建议

- 分析地区销售额时，连接 `orders`、`order_items`、`regions`。
- 分析商品或品类销售额时，连接 `order_items`、`products`。
- 分析月度趋势时，连接 `orders`、`order_items`，按 `DATE_FORMAT(orders.order_date, '%Y-%m')` 分组。

## 注意事项

当前示例库没有退款、折扣、优惠券字段，因此销售额按成交单价直接汇总。
