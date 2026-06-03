# GMV

aliases: GMV, 成交总额, 交易总额, 总成交额
keywords: gmv, 成交, 交易额, 总交易额, 销售额趋势
tables: orders, order_items
fields: orders.order_id, orders.order_date, order_items.quantity, order_items.unit_price

## 业务含义

GMV 表示成交总额，用于衡量一段时间内已经产生订单的商品交易规模。

## 计算口径

在当前示例库中，GMV 与订单明细中的商品数量和成交单价有关：

```sql
SUM(order_items.quantity * order_items.unit_price)
```

如果问题涉及时间趋势，需要使用 `orders.order_date` 做时间维度分组。

## SQL 建议

- 需要连接 `orders` 和 `order_items`。
- 时间筛选使用 `orders.order_date`。
- 月度趋势可以使用 `DATE_FORMAT(orders.order_date, '%Y-%m')`。
- 返回金额时建议使用 `ROUND(..., 2)`。

## 注意事项

当前示例库没有退款表，因此 GMV 不扣除退款金额。
