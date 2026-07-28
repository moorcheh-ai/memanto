# System Design Interview Prep

**Type:** auto-classified
**Source:** claude
**Confidence:** 0.8
**Tags:** claude, ai-conversation
**Created:** 2025-12-10 09:00:00+00:00

---

[User message 1]: I have a system design interview next week. How should I approach designing a URL shortener like bit.ly?

[Assistant message 2]: Follow this framework:

1. **Requirements**: Functional (shorten URL, redirect, custom aliases, analytics) + Non-functional (99.9% uptime, <100ms redirect, handle 100M URLs/day)
2. **Back-of-envelope**: 100M URLs/day = ~1200 writes/sec, ~500 reads/sec (3:1 read:write). Storage: 5 years × 100M × 365 × 500 bytes = ~91TB
3. **API design**: `POST /shorten {long_url}` → `{short_url}`, `GET /{short_code}` → 301 redirect
4. **Database**: Use a key-value store (DynamoDB/Redis) for the mapping. For unique IDs, use a counter service or snowflake ID
5. **Encoding**: Base62 encoding of the ID gives you short codes. 7 chars = 62^7 ≈ 3.5 trillion unique URLs
6. **Caching**: Cache hot URLs in Redis (80/20 rule — 20% of URLs get 80% of traffic)

[User message 3]: How do I handle the analytics part? Like tracking click counts and referrers?

[Assistant message 4]: Use an event-driven approach:

1. **On redirect**: Write an event to Kafka/SQS (async, non-blocking)
2. **Analytics worker**: Consumes events, updates:
   - Click count in Redis (INCR short_code:clicks)
   - Time-series data in TimescaleDB or ClickHouse for dashboards
   - Referrer breakdown in a separate table
3. **API for analytics**: `GET /analytics/{short_code}` reads from Redis (counts) + Timeseries DB (charts)

Key insight: Don't block the redirect on analytics. The redirect should be instant — fire-and-forget the analytics event.

---
*Migration metadata:*
**Source:** claude:conversation
**Claude title:** System Design Interview Prep
**Claude UUID:** conv_claude_003
**Message count:** 4
**Source created_at:** 2025-12-10T09:00:00+00:00
