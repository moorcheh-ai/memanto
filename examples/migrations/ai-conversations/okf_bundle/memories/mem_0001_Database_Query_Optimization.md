# Database Query Optimization

**Type:** auto-classified
**Source:** claude
**Confidence:** 0.8
**Tags:** claude, ai-conversation
**Created:** 2025-12-01 14:00:00+00:00

---

[User message 1]: My PostgreSQL queries are slow on a table with 10 million rows. The main query joins a users table with an orders table. What's the first thing I should check?

[User message 2]: I ran EXPLAIN ANALYZE and it shows a Seq Scan on orders even with the index. The query has a WHERE clause filtering by status = 'pending' AND created_at > now() - interval '7 days'.

---
*Migration metadata:*
**Source:** claude:conversation
**Claude title:** Database Query Optimization
**Claude UUID:** conv_claude_002
**Message count:** 2
**Source created_at:** 2025-12-01T14:00:00+00:00
