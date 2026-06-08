"""
场景A: 上下文开销延迟冲刺 (数据密集型)
- 模拟密集技术日志/长篇医疗记录
- 测量每轮对话的总 token 消耗和检索延迟
"""
from __future__ import annotations

from backends.base import MemoryEntry

# 技术日志数据集 - 模拟密集的系统日志和调试信息
TECHNICAL_LOGS: list[MemoryEntry] = [
    MemoryEntry(
        content="2026-06-01 08:15:32 [ERROR] PostgreSQL connection pool exhausted. "
                "Active connections: 100/100. Waiting threads: 23. "
                "Pool config: min=10, max=100, timeout=30s. "
                "Last successful connection: 08:14:58. "
                "Stack trace: connection_pool.py:245 -> acquire() -> TimeoutError",
        memory_type="error",
        metadata={"source": "postgres-01", "severity": "CRITICAL"},
    ),
    MemoryEntry(
        content="2026-06-01 08:16:01 [WARN] Redis cache hit ratio dropped to 23.4% "
                "(baseline: 89.2%). Key eviction count: 15,234 in last 5 minutes. "
                "Memory usage: 7.8GB/8GB. Eviction policy: allkeys-lru. "
                "Hot keys: session:usr:* (42% of traffic), rate:api:* (31%)",
        memory_type="observation",
        metadata={"source": "redis-01", "severity": "WARNING"},
    ),
    MemoryEntry(
        content="2026-06-01 08:17:45 [INFO] Kubernetes pod deployment prod-api-7f8b9 "
                "scaled from 3 to 12 replicas due to CPU utilization spike (89% -> 94%). "
                "HPA metrics: cpu=94%, memory=67%, custom:requests_per_sec=4521. "
                "Target: cpu=70%. Previous scale event: 06-01 07:45:00 (2->3)",
        memory_type="event",
        metadata={"source": "k8s-prod", "severity": "INFO"},
    ),
    MemoryEntry(
        content="2026-06-01 08:18:22 [ERROR] Payment gateway webhook timeout. "
                "Provider: Stripe. Endpoint: /webhooks/stripe. "
                "Timeout after 30s. Payload size: 2.3MB. "
                "Retry count: 3/3. Last successful webhook: 08:10:15. "
                "Affected orders: ORD-2026-7891 through ORD-2026-7894. "
                "Fallback: queue payment-events-legacy for manual processing",
        memory_type="error",
        metadata={"source": "payment-service", "severity": "CRITICAL"},
    ),
    MemoryEntry(
        content="2026-06-01 08:19:05 [INFO] ML model inference pipeline completed batch #4521. "
                "Model: yolov8x-seg. Input: 1,247 images (avg 2.1MB each). "
                "Output: 1,247 segmentation masks. Total inference time: 342s. "
                "GPU utilization: 98.2%. Memory: 31.2GB/36GB VRAM. "
                "Avg latency per image: 274ms. P95: 312ms. P99: 445ms.",
        memory_type="observation",
        metadata={"source": "ml-pipeline", "severity": "INFO"},
    ),
    MemoryEntry(
        content="2026-06-01 08:20:18 [WARN] SSL certificate for api.example.com expires in 7 days. "
                "Issuer: Let's Encrypt. Serial: 04:AB:CD:EF:12:34. "
                "Auto-renewal failed: DNS challenge timeout. "
                "Manual intervention required. Previous renewal: 2026-03-03. "
                "Backup cert available: api-backup.example.com",
        memory_type="observation",
        metadata={"source": "cert-monitor", "severity": "WARNING"},
    ),
    MemoryEntry(
        content="2026-06-01 08:21:33 [ERROR] Elasticsearch cluster health: RED. "
                "Unassigned shards: 47. Primary shards affected: 12. "
                "Indices impacted: logs-2026.06, metrics-2026.06, traces-2026.06. "
                "Disk usage: node-1 (91%), node-2 (87%), node-3 (94%). "
                "Watermark: flood_stage=95%. Recovery in progress.",
        memory_type="error",
        metadata={"source": "elasticsearch-01", "severity": "CRITICAL"},
    ),
    MemoryEntry(
        content="2026-06-01 08:22:07 [INFO] Database migration v2.14.0 completed successfully. "
                "Applied 23 migrations. Tables modified: users, sessions, audit_log. "
                "New columns: users.mfa_enabled, users.last_login_ip. "
                "Index created: audit_log_timestamp_idx. Duration: 4m 32s. "
                "Zero downtime achieved using online schema change (gh-ost).",
        memory_type="event",
        metadata={"source": "migration-runner", "severity": "INFO"},
    ),
    MemoryEntry(
        content="2026-06-01 08:23:51 [WARN] CDN cache invalidation incomplete. "
                "Distribution: CloudFront. Invalidation ID: I20260601-XXXXX. "
                "Status: 847/1024 paths invalidated. Failed paths: /api/v2/*, /static/js/*. "
                "Error: ThrottlingException. Retry scheduled at 08:30:00. "
                "Impact: 17% of users may see stale content",
        memory_type="observation",
        metadata={"source": "cdn-monitor", "severity": "WARNING"},
    ),
    MemoryEntry(
        content="2026-06-01 08:24:15 [ERROR] gRPC service mesh: 3 upstream timeouts in last 60s. "
                "Service: order-service -> inventory-service. "
                "Timeout: 5000ms. Actual p99: 12,340ms. "
                "Circuit breaker state: OPEN for inventory-service:grpc. "
                "Fallback: cache-based inventory check (stale data up to 30s). "
                "Root cause: inventory-service pod restart loop (OOMKilled)",
        memory_type="error",
        metadata={"source": "service-mesh", "severity": "CRITICAL"},
    ),
]

# 检索查询 - 用于测试检索准确率
RETRIEVAL_QUERIES = [
    "What caused the PostgreSQL connection pool issue?",
    "Which services had CRITICAL errors in the last hour?",
    "What is the current state of the Elasticsearch cluster?",
    "How many pods were scaled and why?",
    "What payment orders were affected by the webhook timeout?",
]

# 期望检索结果 (golden answers) - 用于 LLM-as-a-Judge 评分
GOLDEN_ANSWERS = {
    "What caused the PostgreSQL connection pool issue?": [
        "PostgreSQL connection pool exhausted, active connections 100/100, 23 waiting threads",
    ],
    "Which services had CRITICAL errors in the last hour?": [
        "PostgreSQL, Payment gateway, Elasticsearch, gRPC service mesh",
    ],
    "What is the current state of the Elasticsearch cluster?": [
        "RED health, 47 unassigned shards, disk usage near flood_stage watermark",
    ],
    "How many pods were scaled and why?": [
        "prod-api scaled from 3 to 12 replicas due to CPU utilization spike 89% to 94%",
    ],
    "What payment orders were affected by the webhook timeout?": [
        "ORD-2026-7891 through ORD-2026-7894",
    ],
}
