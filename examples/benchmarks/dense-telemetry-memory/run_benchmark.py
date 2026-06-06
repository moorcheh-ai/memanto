#!/usr/bin/env python3
"""Dense telemetry memory benchmark for the Memanto showdown (#639).

Scenario A from the challenge brief: feed agents dense, shifting technical logs
(ICU vitals, lab panels, medication titrations, device alarms) and measure the
accuracy vs. resource-footprint tradeoff.

The benchmark is offline and deterministic. It models a clinical monitoring
agent that ingests high-volume telemetry over multiple shifts. Append-only
graph-style memory recalls facts but injects superseded vitals, stale medication
orders, and noisy device chatter. A recent-window log is compact but forgets
durable allergies and baseline diagnoses. The active digest acts like a Memanto
companion: typed current facts, explicit supersession, and question-scoped
retrieval.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())
        if token
        not in {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "which",
            "what",
            "patient",
            "shift",
        }
    }


def token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


@dataclass(frozen=True)
class ClinicalFact:
    key: str
    value: str
    tags: tuple[str, ...]
    evidence: str
    session: str


@dataclass(frozen=True)
class TelemetryEvent:
    session: str
    source: str
    text: str
    facts: tuple[ClinicalFact, ...] = ()


@dataclass(frozen=True)
class Query:
    question: str
    must_have: tuple[str, ...]
    must_not_have: tuple[str, ...] = ()
    session_cutoff: str | None = None


# Dense telemetry corpus: raw device output mixed with clinically relevant facts.
EVENTS: tuple[TelemetryEvent, ...] = (
    TelemetryEvent(
        "shift-01",
        "admission",
        "ADT feed MRN-88421 admit 2026-05-28T06:12Z ward=ICU-7 bed=B12 attending=Dr. Okonkwo "
        "primary_dx=community_acquired_pneumonia secondary_dx=type2_diabetes_hba1c_7.8 "
        "allergy_documented=penicillin_anaphylaxis severity=severe "
        "baseline_spo2_target=92% baseline_map_target=65mmHg noise_floor=0.02",
        (
            ClinicalFact(
                "patient.mrn",
                "MRN-88421",
                ("identity", "current"),
                "Stable patient identifier across shifts.",
                "shift-01",
            ),
            ClinicalFact(
                "clinical.primary_dx",
                "Community-acquired pneumonia",
                ("diagnosis", "current"),
                "Admission diagnosis from attending note.",
                "shift-01",
            ),
            ClinicalFact(
                "clinical.allergy",
                "Penicillin — anaphylaxis (severe); avoid all beta-lactam antibiotics.",
                ("allergy", "safety", "current"),
                "Documented severe allergy at admission.",
                "shift-01",
            ),
            ClinicalFact(
                "care.attending",
                "Dr. Okonkwo",
                ("team", "current"),
                "Attending of record at admission.",
                "shift-01",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-01",
        "vitals",
        "Vitals panel Philips monitor stream seq=1042 ts=06:45Z hr=104 rr=24 bp=98/58 map=71 spo2=89% "
        "temp=38.6C device_alarm=spo2_below_threshold nurse_note=titrating_o2 respiratory=nc_2L",
        (
            ClinicalFact(
                "vitals.latest",
                "HR 104, RR 24, BP 98/58 (MAP 71), SpO2 89%, temp 38.6°C — hypoxic, titrating O2.",
                ("vitals", "current"),
                "Early-shift vitals before O2 escalation.",
                "shift-01",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-01",
        "labs",
        "LIS panel CBC WBC=14.2 Hgb=11.1 Plt=198 BMP Na=136 K=4.1 Cr=1.0 glucose=212 "
        "ABG pH=7.34 pCO2=44 pO2=61 lactate=1.8 procalcitonin=0.9",
        (
            ClinicalFact(
                "labs.inflammatory",
                "WBC 14.2, procalcitonin 0.9, glucose 212 — inflammatory response with hyperglycemia.",
                ("labs", "current"),
                "Admission labs consistent with infection and diabetes.",
                "shift-01",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-01",
        "orders",
        "eMAR start ceftriaxone 1g IV q24h (allergy override pending pharm review) "
        "start azithromycin 500mg IV daily insulin_sliding_scale basal=8u "
        "oxygen_nc_2L maintain_spo2>=92%",
        (
            ClinicalFact(
                "med.antibiotic",
                "Ceftriaxone 1g IV q24h + azithromycin 500mg IV daily (pending allergy review).",
                ("medication", "stale"),
                "Initial antibiotic plan before allergy reconciliation.",
                "shift-01",
            ),
            ClinicalFact(
                "resp.support",
                "Nasal cannula 2 L/min; target SpO2 ≥ 92%.",
                ("respiratory", "stale"),
                "Initial oxygen plan before escalation.",
                "shift-01",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-02",
        "pharmacy",
        "Pharmacy alert: penicillin anaphylaxis on file. Ceftriaxone (beta-lactam) contraindicated. "
        "Recommend levofloxacin 750mg IV q24h + azithromycin continue. Attending paged.",
        (
            ClinicalFact(
                "med.antibiotic",
                "Levofloxacin 750mg IV q24h + azithromycin 500mg IV daily (penicillin allergy safe).",
                ("medication", "current", "safety"),
                "Pharmacy replaced beta-lactam after allergy reconciliation.",
                "shift-02",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-02",
        "vitals",
        "Vitals panel Philips monitor stream seq=2288 ts=14:10Z hr=96 rr=22 bp=104/62 map=76 spo2=93% "
        "temp=38.1C fio2_nc=4L nurse_note=improved_after_abx_switch respiratory=nc_4L",
        (
            ClinicalFact(
                "vitals.latest",
                "HR 96, RR 22, BP 104/62 (MAP 76), SpO2 93%, temp 38.1°C on 4L NC — improving.",
                ("vitals", "current"),
                "Mid-shift vitals after antibiotic change and O2 titration.",
                "shift-02",
            ),
            ClinicalFact(
                "resp.support",
                "Nasal cannula 4 L/min; target SpO2 ≥ 92%.",
                ("respiratory", "current"),
                "O2 escalated to 4L after initial hypoxia.",
                "shift-02",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-02",
        "device_noise",
        "Bed exit sensor false_positive x3 infusion_pump_beep resolved_cable_loose "
        "telemetry_packet_loss=0.4% gateway_reboot_scheduled maint_ticket=ICU-4412",
    ),
    TelemetryEvent(
        "shift-03",
        "vitals",
        "Vitals panel Philips monitor stream seq=3310 ts=22:05Z hr=88 rr=18 bp=112/68 map=83 spo2=95% "
        "temp=37.4C fio2_hfnc=40%/30L nurse_note=weaning_candidate respiratory=hfnc",
        (
            ClinicalFact(
                "vitals.latest",
                "HR 88, RR 18, BP 112/68 (MAP 83), SpO2 95%, temp 37.4°C on HFNC 40%/30L.",
                ("vitals", "current"),
                "Night-shift vitals show recovery trend.",
                "shift-03",
            ),
            ClinicalFact(
                "resp.support",
                "HFNC 40% FiO2 at 30 L/min; weaning candidate if SpO2 stable overnight.",
                ("respiratory", "current"),
                "Escalated to HFNC after NC plateau; now stable.",
                "shift-03",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-03",
        "labs",
        "Repeat BMP glucose=168 lactate=1.2 procalcitonin=0.4 WBC=10.1 — trending down.",
        (
            ClinicalFact(
                "labs.inflammatory",
                "WBC 10.1, procalcitonin 0.4, glucose 168 — improving inflammatory markers.",
                ("labs", "current"),
                "Follow-up labs show treatment response.",
                "shift-03",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-04",
        "attending",
        "Dr. Okonkwo handoff: patient clinically improved. If SpO2 ≥ 94% on HFNC 30%/25L "
        "by morning, step down to ward-12. Continue levofloxacin day 3/7. "
        "Endocrinology consult for insulin regimen before discharge.",
        (
            ClinicalFact(
                "care.plan",
                "Step-down to ward-12 if SpO2 ≥ 94% on HFNC 30%/25L; continue levofloxacin day 3/7; endocrine consult before discharge.",
                ("plan", "current"),
                "Attending handoff with disposition criteria.",
                "shift-04",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-04",
        "vitals",
        "Vitals panel Philips monitor stream seq=4102 ts=06:20Z hr=82 rr=16 bp=118/72 map=87 spo2=96% "
        "temp=36.9C fio2_hfnc=30%/25L respiratory=hfnc_weaning",
        (
            ClinicalFact(
                "vitals.latest",
                "HR 82, RR 16, BP 118/72 (MAP 87), SpO2 96%, temp 36.9°C on HFNC 30%/25L.",
                ("vitals", "current"),
                "Morning vitals meet step-down oxygen targets.",
                "shift-04",
            ),
            ClinicalFact(
                "resp.support",
                "HFNC 30% FiO2 at 25 L/min; meets step-down SpO2 threshold.",
                ("respiratory", "current"),
                "Weaned per attending criteria.",
                "shift-04",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-05",
        "transfer",
        "Transfer order executed destination=ward-12 bed=W4 nurse_ratio=1:4 "
        "antibiotic_day=4/7 levofloxacin_due=14:00Z glucose_monitor_q6h",
        (
            ClinicalFact(
                "care.location",
                "Ward-12 bed W4 (step-down from ICU-7).",
                ("location", "current"),
                "Patient stepped down after meeting criteria.",
                "shift-05",
            ),
            ClinicalFact(
                "med.antibiotic",
                "Levofloxacin day 4/7; next dose 14:00Z; azithromycin completed day 3.",
                ("medication", "current"),
                "Updated antibiotic course on transfer.",
                "shift-05",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-05",
        "device_noise",
        "Ward telemetry gateway latency_p95=180ms packet_loss=0.1% "
        "bedside_monitor_firmware=4.2.1 heartbeat_ok",
    ),
    TelemetryEvent(
        "shift-06",
        "endocrine",
        "Endocrine note: switch from sliding scale to basal-bolus — glargine 12u qHS, "
        "lispro with meals per carb ratio 1:10. Target fasting glucose 100-140.",
        (
            ClinicalFact(
                "med.diabetes",
                "Basal-bolus: glargine 12u qHS + lispro with meals (1:10 carb ratio); target fasting glucose 100-140.",
                ("medication", "current", "endocrine"),
                "Endocrine consult finalized discharge insulin plan.",
                "shift-06",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-06",
        "labs",
        "Pre-discharge BMP glucose=142 Cr=0.9 — renal function stable, glycemic control improved.",
        (
            ClinicalFact(
                "labs.inflammatory",
                "Glucose 142, creatinine 0.9 — stable renal function, improved glycemic control.",
                ("labs", "current"),
                "Pre-discharge labs support outpatient transition.",
                "shift-06",
            ),
        ),
    ),
    TelemetryEvent(
        "shift-07",
        "discharge",
        "Discharge summary attending=Dr. Okonkwo dx=pneumonia_resolved "
        "allergy=penicillin_anaphylaxis rx=levofloxacin_finish_3d_oral "
        "insulin=glargine_12u_qHS_lispro_meals follow_up=pulmonology_2w",
        (
            ClinicalFact(
                "care.plan",
                "Discharged home; finish 3 days oral levofloxacin; continue glargine 12u qHS + lispro with meals; pulmonology follow-up in 2 weeks.",
                ("plan", "current"),
                "Final discharge plan supersedes ICU step-down criteria.",
                "shift-07",
            ),
            ClinicalFact(
                "care.location",
                "Discharged home (2026-06-04).",
                ("location", "current"),
                "Patient no longer inpatient.",
                "shift-07",
            ),
        ),
    ),
)


QUERIES: tuple[Query, ...] = (
    Query(
        "What antibiotic regimen is currently active and safe given documented allergies?",
        ("levofloxacin", "azithromycin"),
        ("ceftriaxone",),
    ),
    Query(
        "What is the patient's severe allergy and what must be avoided?",
        ("penicillin", "anaphylaxis", "beta-lactam"),
        (),
    ),
    Query(
        "What are the latest vital signs and current respiratory support?",
        ("spo2", "hfnc", "30%"),
        ("spo2=89%", "2 l/min"),
    ),
    Query(
        "What is the current care location or disposition?",
        ("discharged home",),
        ("icu-7", "ward-12 bed w4"),
    ),
    Query(
        "What is the current diabetes medication plan?",
        ("glargine", "lispro", "1:10"),
        ("sliding scale", "basal=8u"),
    ),
    Query(
        "What do the most recent inflammatory labs show?",
        ("glucose 142", "creatinine 0.9"),
        ("wbc=14.2", "procalcitonin=0.9"),
    ),
    Query(
        "Who is the attending physician of record?",
        ("dr. okonkwo",),
    ),
    Query(
        "What is the current discharge or follow-up plan?",
        ("oral levofloxacin", "pulmonology", "2 weeks"),
        ("step-down to ward-12",),
    ),
    Query(
        "What is the patient MRN?",
        ("mrn-88421",),
    ),
)


SESSION_ORDER = (
    "shift-01",
    "shift-02",
    "shift-03",
    "shift-04",
    "shift-05",
    "shift-06",
    "shift-07",
)


class Backend:
    name = "backend"

    def retrieve(self, question: str) -> str:
        raise NotImplementedError


class AppendOnlyLog(Backend):
    """Graph-style dump: every telemetry event, lexical retrieval."""

    name = "append_only_log"

    def __init__(self, events: Iterable[TelemetryEvent]) -> None:
        self.events = list(events)

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        ranked = []
        for event in self.events:
            overlap = len(query_terms & tokenize(event.text))
            if overlap:
                ranked.append((overlap, event.session, event))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        # Graph-style dumps surface every overlapping record, not just the newest.
        return "\n".join(event.text for _, _, event in ranked)


class WindowedRecentLog(Backend):
    """Recent-window log: compact but forgets durable constraints."""

    name = "windowed_recent_log"

    def __init__(self, events: Iterable[TelemetryEvent], window_size: int = 4) -> None:
        self.events = list(events)[-window_size:]

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        hits = [
            event.text
            for event in self.events
            if query_terms & tokenize(event.text)
        ]
        return "\n".join(hits)


class ActiveTelemetryDigest(Backend):
    """Memanto-style active digest: one current fact per key, scoped retrieval."""

    name = "active_telemetry_digest"

    def __init__(self, events: Iterable[TelemetryEvent]) -> None:
        facts: dict[str, ClinicalFact] = {}
        for event in events:
            for fact in event.facts:
                facts[fact.key] = fact
        self.facts = facts

    def retrieve(self, question: str) -> str:
        query_terms = tokenize(question)
        ranked = []
        for fact in self.facts.values():
            haystack = " ".join((fact.key, fact.value, " ".join(fact.tags), fact.evidence))
            score = len(query_terms & tokenize(haystack))
            if score:
                ranked.append((score, fact.key, fact))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        lines = [
            f"{fact.key}: {fact.value} (session {fact.session})"
            for _, _, fact in ranked[:3]
        ]
        return "\n".join(lines)


def events_through_session(session: str) -> tuple[TelemetryEvent, ...]:
    if session not in SESSION_ORDER:
        raise ValueError(f"Unknown session: {session}")
    cutoff = SESSION_ORDER.index(session) + 1
    allowed = set(SESSION_ORDER[:cutoff])
    return tuple(event for event in EVENTS if event.session in allowed)


def signal_tokens(context: str, query: Query) -> int:
    lowered = context.lower()
    hits = sum(1 for term in query.must_have if term.lower() in lowered)
    return hits * 8


def evaluate_backend(
    backend: Backend,
    queries: Iterable[Query],
    *,
    events: Iterable[TelemetryEvent] | None = None,
) -> dict[str, object]:
    rows = []
    latencies_ms = []
    total_tokens = 0
    total_signal = 0
    correct = 0
    stale_conflicts = 0

    for query in queries:
        start = time.perf_counter()
        context = backend.retrieve(query.question)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        normalized = context.lower()
        has_expected = all(value.lower() in normalized for value in query.must_have)
        has_stale = any(value.lower() in normalized for value in query.must_not_have)
        ok = has_expected and not has_stale

        if ok:
            correct += 1
        if has_stale:
            stale_conflicts += 1

        retrieved_tokens = token_count(context)
        signal = signal_tokens(context, query)
        total_tokens += retrieved_tokens
        total_signal += signal
        rows.append(
            {
                "question": query.question,
                "retrieved_tokens": retrieved_tokens,
                "signal_tokens": signal,
                "correct": ok,
                "stale_conflict": has_stale,
                "context_preview": context[:240],
            }
        )

    query_count = len(rows)
    avg_tokens = total_tokens / query_count
    signal_noise = (total_signal / total_tokens) if total_tokens else 0.0
    ingestion_tokens = sum(token_count(event.text) for event in (events or EVENTS))

    return {
        "backend": backend.name,
        "accuracy": round(correct / query_count, 4),
        "avg_retrieved_tokens": round(avg_tokens, 2),
        "total_ingestion_tokens": ingestion_tokens,
        "p95_latency_ms": round(
            statistics.quantiles(latencies_ms, n=20, method="inclusive")[18],
            4,
        ),
        "stale_conflict_rate": round(stale_conflicts / query_count, 4),
        "signal_noise_ratio": round(signal_noise, 4),
        "rows": rows,
    }


def degradation_curve(backend_factory, queries: Iterable[Query]) -> list[dict[str, object]]:
    curve = []
    for session in SESSION_ORDER:
        events = events_through_session(session)
        backend = backend_factory(events)
        summary = evaluate_backend(backend, queries, events=events)
        curve.append(
            {
                "session": session,
                "accuracy": summary["accuracy"],
                "avg_retrieved_tokens": summary["avg_retrieved_tokens"],
            }
        )
    return curve


def run() -> dict[str, object]:
    backends: tuple[Backend, ...] = (
        AppendOnlyLog(EVENTS),
        WindowedRecentLog(EVENTS),
        ActiveTelemetryDigest(EVENTS),
    )
    results = [evaluate_backend(backend, QUERIES) for backend in backends]

    degradation = {
        "append_only_log": degradation_curve(AppendOnlyLog, QUERIES),
        "windowed_recent_log": degradation_curve(WindowedRecentLog, QUERIES),
        "active_telemetry_digest": degradation_curve(ActiveTelemetryDigest, QUERIES),
    }

    return {
        "benchmark": "dense_telemetry_memory",
        "description": (
            "Offline Scenario-A benchmark for dense ICU telemetry logs with shifting vitals, "
            "medication changes, and disposition updates."
        ),
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "llm_backend": "none (deterministic golden-set scoring)",
            "prompt_system": "n/a — retrieval-only evaluation",
        },
        "event_count": len(EVENTS),
        "query_count": len(QUERIES),
        "session_count": len(SESSION_ORDER),
        "results": results,
        "cross_session_degradation": degradation,
    }


def to_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Dense Telemetry Memory Results",
        "",
        "Scenario A: context-overhead and latency sprint on dense ICU telemetry logs.",
        "",
        "| Backend | Accuracy | Avg retrieved tokens | Total ingestion tokens | p95 latency ms | Stale conflict rate | Signal/noise |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["results"]:
        lines.append(
            "| {backend} | {accuracy:.1%} | {avg_retrieved_tokens} | {total_ingestion_tokens} | {p95_latency_ms} | {stale_conflict_rate:.1%} | {signal_noise_ratio:.2f} |".format(
                **item
            )
        )

    lines.extend(["", "## Cross-session degradation (accuracy)", ""])
    for backend_name, curve in report["cross_session_degradation"].items():
        accuracies = ", ".join(f"{point['session']}={point['accuracy']:.0%}" for point in curve)
        lines.append(f"- **{backend_name}**: {accuracies}")

    lines.extend(
        [
            "",
            "The active telemetry digest keeps one current fact per clinical key, suppresses "
            "superseded vitals and contraindicated medications, and retrieves only question-relevant "
            "evidence. Append-only logs demonstrate token inflation and stale conflicts; recent-window "
            "logs trade footprint for lost durable allergies and baseline diagnoses.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown summary output path.")
    args = parser.parse_args()

    report = run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(report), encoding="utf-8")
    if not args.output and not args.markdown:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
