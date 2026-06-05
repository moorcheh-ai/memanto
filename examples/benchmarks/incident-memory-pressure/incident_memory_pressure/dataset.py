from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncidentRecord:
    session: int
    service: str
    key: str
    kind: str
    text: str
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True)
class IncidentQuery:
    service: str
    prompt: str
    expected_fragments: tuple[str, ...]
    stale_fragments: tuple[str, ...]


def incident_records() -> list[IncidentRecord]:
    return [
        IncidentRecord(
            1,
            "payments",
            "payments.owner",
            "owner",
            "Payments owner is Aria. Page Aria only after retry budget is exhausted.",
        ),
        IncidentRecord(
            1,
            "payments",
            "payments.runbook",
            "runbook",
            "Payments runbook v1 says restart checkout-worker before checking PSP health.",
        ),
        IncidentRecord(
            2,
            "payments",
            "payments.status",
            "status",
            "Customer status wording: payment authorization delays for EU cards.",
        ),
        IncidentRecord(
            3,
            "search",
            "search.owner",
            "owner",
            "Search owner is Dev. Escalate relevance regressions to Dev.",
        ),
        IncidentRecord(
            3,
            "search",
            "search.runbook",
            "runbook",
            "Search runbook v1 says rebuild the synonym index before rolling pods.",
        ),
        IncidentRecord(
            4,
            "notifications",
            "notifications.owner",
            "owner",
            "Notifications owner is Mira. Mira handles provider throttling events.",
        ),
        IncidentRecord(
            5,
            "payments",
            "payments.runbook",
            "runbook",
            "Payments runbook v2 says check PSP health first, then drain checkout-worker.",
            supersedes=("payments.runbook",),
        ),
        IncidentRecord(
            6,
            "payments",
            "payments.mitigation",
            "decision",
            "Payments mitigation: rollback fraud-rule bundle 2026.06.05-b after spike.",
        ),
        IncidentRecord(
            7,
            "search",
            "search.status",
            "status",
            "Customer status wording: search filters may lag up to five minutes.",
        ),
        IncidentRecord(
            8,
            "search",
            "search.runbook",
            "runbook",
            "Search runbook v2 says disable live synonym expansion before rebuild.",
            supersedes=("search.runbook",),
        ),
        IncidentRecord(
            9,
            "notifications",
            "notifications.status",
            "status",
            "Customer status wording: SMS delivery is delayed for APAC recipients.",
        ),
        IncidentRecord(
            10,
            "notifications",
            "notifications.runbook",
            "runbook",
            "Notifications runbook v1 says retry Twilio webhooks with exponential backoff.",
        ),
        IncidentRecord(
            11,
            "payments",
            "payments.owner",
            "owner",
            "Payments owner changed to Noor. Noor owns checkout and PSP escalation.",
            supersedes=("payments.owner",),
        ),
        IncidentRecord(
            12,
            "payments",
            "payments.status",
            "status",
            "Customer status wording: checkout is stable; EU card backlog is draining.",
            supersedes=("payments.status",),
        ),
        IncidentRecord(
            13,
            "search",
            "search.owner",
            "owner",
            "Search owner changed to Lin. Lin owns relevance rollback decisions.",
            supersedes=("search.owner",),
        ),
        IncidentRecord(
            14,
            "notifications",
            "notifications.runbook",
            "runbook",
            "Notifications runbook v2 says pause APAC SMS batch jobs before retries.",
            supersedes=("notifications.runbook",),
        ),
        IncidentRecord(
            15,
            "notifications",
            "notifications.owner",
            "owner",
            "Notifications owner changed to Theo. Theo owns provider throttling events.",
            supersedes=("notifications.owner",),
        ),
        IncidentRecord(
            16,
            "search",
            "search.status",
            "status",
            "Customer status wording: search relevance is normal after synonym rollback.",
            supersedes=("search.status",),
        ),
    ]

def incident_queries() -> list[IncidentQuery]:
    return [
        IncidentQuery(
            "payments",
            "What is the current payments runbook?",
            ("check PSP health first", "drain checkout-worker"),
            ("restart checkout-worker before checking PSP health",),
        ),
        IncidentQuery(
            "payments",
            "Who owns payments escalation now?",
            ("Noor owns checkout", "PSP escalation"),
            ("Payments owner is Aria",),
        ),
        IncidentQuery(
            "payments",
            "What should customer support say about payments?",
            ("checkout is stable", "EU card backlog is draining"),
            ("payment authorization delays for EU cards",),
        ),
        IncidentQuery(
            "search",
            "What is the current search runbook?",
            ("disable live synonym expansion", "before rebuild"),
            ("rebuild the synonym index before rolling pods",),
        ),
        IncidentQuery(
            "search",
            "Who owns search relevance rollback decisions?",
            ("Search owner changed to Lin", "rollback decisions"),
            ("Search owner is Dev",),
        ),
        IncidentQuery(
            "search",
            "What is the current public search status?",
            ("search relevance is normal", "synonym rollback"),
            ("filters may lag up to five minutes",),
        ),
        IncidentQuery(
            "notifications",
            "What is the current notifications runbook?",
            ("pause APAC SMS batch jobs", "before retries"),
            ("retry Twilio webhooks",),
        ),
        IncidentQuery(
            "notifications",
            "Who owns provider throttling now?",
            ("Notifications owner changed to Theo", "provider throttling"),
            ("Notifications owner is Mira",),
        ),
    ]
