# Database Query Optimization

**Type:** auto-classified
**Source:** claude
**Confidence:** 0.8
**Tags:** claude, ai-conversation
**Created:** 2025-12-01 14:00:00+00:00

---

[User message 1]: My PostgreSQL queries are slow on a table with 10 million rows. The main query joins a users table with an orders table. What's the first thing I should check?

[Assistant message 2]: Start with `EXPLAIN ANALYZE` on your query. The most common causes:

1. **Missing indexes** on join columns (orders.user_id should be indexed)
2. **Seq scans** instead of index scans
3. **Poor selectivity** — if a filter returns >15% of rows, PostgreSQL may prefer a seq scan

Quick wins:
```sql
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_created_at ON orders(created_at);
```

Then run `ANALYZE orders;` to update statistics.

[User message 3]: I ran EXPLAIN ANALYZE and it shows a Seq Scan on orders even with the index. The query has a WHERE clause filtering by status = 'pending' AND created_at > now() - interval '7 days'.

[Assistant message 4]: That's likely a selectivity issue. Try a **composite index** that matches your WHERE clause:

```sql
CREATE INDEX idx_orders_status_created 
  ON orders(status, created_at DESC) 
  WHERE status = 'pending';
```

This is a **partial index** — it only indexes pending orders, making it much smaller and faster. The partial index is ideal here because you're filtering on a low-cardinality column (`status`).

After creating, run `EXPLAIN ANALYZE` again. You should see an Index Scan instead of Seq Scan.

---
*Migration metadata:*
**Source:** claude:conversation
**Claude title:** Database Query Optimization
**Claude UUID:** conv_claude_002
**Message count:** 4
**Source created_at:** 2025-12-01T14:00:00+00:00
