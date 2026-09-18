#!/usr/bin/env python3
"""
Before/after **query parity** for the migration — offline, credential-free.

The question this answers: *after migrating, does asking the same thing still
reach the same piece of the conversation?* A migration can preserve every byte
and still be useless if the answers stop being findable.

How it works — deliberately transparent, no model, no network:

* **Before** corpus: the raw OpenAI Responses items in
  ``sample/source/session_snapshot.json`` — the real SDK capture.
* **After** corpus: the memories Memanto would actually store, produced by
  running the repository's own ``load_okf_bundle`` + ``map_okf`` over the
  committed OKF bundle.
* **Question-only rows are excluded from both.** A user turn that just asks
  something ("What is the deploy window?") carries no answer; left in, a query
  "succeeds" by retrieving its own question back, which proves nothing.
* Every query carries an explicit **expected fact set** copied from the scripted
  run (``QUERIES``), and where the scenario contains a correction, the
  **superseded** facts it replaced.
* The same retriever runs on both corpora: IDF-weighted cosine, top-K recall,
  extended forward with later items that revise a hit — so a correction is never
  missed just because it is worded differently from what it corrects.
* A query **passes** only when *both* sides retrieve answer-bearing evidence
  covering >= 80% of its expected facts, the newer evidence beats any superseded
  evidence retrieved alongside it, and the answers rest on a shared concept
  (a merged tool call + result and the user's own statement of the same thing
  count as equivalent — identical row ids are not required).

**Every query must pass.** The gate is 100%, not a majority: a migration that
loses one answer has lost it.

**This is preservation / retrievability parity, not live cloud recall.** No
Moorcheh call is made and none is simulated: it measures that the migrated
corpus still answers the same questions from the same evidence.

    python parity_check.py                       # print the report
    python parity_check.py --json out.json       # and write it
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "sample" / "source" / "session_snapshot.json"
BUNDLE = HERE / "sample" / "okf"
REPORT = HERE / "sample" / "evidence" / "adapter-report.json"
SESSION_ID = "workspace-buddy-demo"

#: Every question must keep its answer — the gate is all of them, not a majority.
PARITY_THRESHOLD = 1.0

#: Share of a question's expected facts that the retrieved evidence must carry,
#: on each side independently.
FACT_COVERAGE = 0.80

#: A retrieval with no lexical overlap at all is not evidence of anything.
MIN_SCORE = 0.01

#: How many memories a recall returns. A memory layer is queried this way — you
#: get the top few and read them — so coverage is measured over the set.
TOP_K = 3

#: Two items this similar are talking about the same thing. When the later one
#: revises the earlier, answering from the earlier alone would be wrong, so the
#: recall set is extended forward. Without this a lexical scorer happily returns
#: only the superseded answer, because a correction rarely repeats the original
#: wording ("Correction: the deploy window moved to Thursday" shares almost
#: nothing with "the platform team's deploy window is Tuesday").
SUPERSEDE_SIMILARITY = 0.30

#: The extension is deliberately tight. Migrated memories all carry the same
#: ``[Supporting data]`` footer, which inflates document-to-document similarity —
#: unbounded, the step drags in most of the corpus and "coverage" then only
#: proves the facts exist *somewhere*. So a revision must also still be relevant
#: to the original query, and each hit contributes at most this many.
MAX_REVISIONS_PER_HIT = 1


@dataclass(frozen=True)
class Query:
    """A question plus the facts a correct answer has to contain.

    ``expects`` and ``superseded`` are phrases copied out of the real scripted
    run (see ``generate_session.py``); a phrase counts as present when all of its
    words appear in the retrieved text. ``superseded`` names the *stale* answer,
    so a correction that lands later must out-rank it.
    """

    question: str
    expects: tuple[str, ...]
    superseded: tuple[str, ...] = ()


#: One question per topic the scenario covers, worded as a user would ask it
#: rather than as a copy of the source text, so retrieval has to do real work.
QUERIES: tuple[Query, ...] = (
    Query(
        "When does the platform team deploy?",
        expects=("Thursday", "09:00 UTC"),
        # Turn 3's calendar lookup said Tuesday; turn 4 corrected it.
        superseded=("Tuesday 14:00-16:00",),
    ),
    Query(
        "Which database does the orders service run on?",
        expects=("PostgreSQL 16",),
    ),
    Query(
        "When is the migration plan due?",
        expects=("2026-08-14", "migration plan"),
    ),
    Query(
        "Should answers be short or detailed with bullet points?",
        expects=("detailed", "bullet points"),
        # Turn 1 asked for three sentences; turn 5 reversed it.
        superseded=("three sentences",),
    ),
    Query(
        "Why did the staging rollout fail?",
        expects=("pgbouncer", "connection pool"),
    ),
    Query(
        "What incident was filed for the connection pool?",
        expects=("INC-2141", "pgbouncer"),
    ),
    Query(
        "Which tool looked up the team calendar?",
        expects=("lookup_team_calendar",),
    ),
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by did do does for from has have how i in is it its of on
    or should that the their to was were what when which who why will with you your""".split()
)


class ParityError(Exception):
    """Raised when the parity evidence cannot be produced."""


# ---------------------------------------------------------------------------
# Retrieval — small enough to audit by eye
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return [
        t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS
    ]


def _idf(corpus: list[list[str]]) -> dict[str, float]:
    """Standard smoothed inverse document frequency."""
    n = len(corpus)
    seen: dict[str, int] = {}
    for doc in corpus:
        for token in set(doc):
            seen[token] = seen.get(token, 0) + 1
    return {t: math.log((n + 1) / (df + 1)) + 1.0 for t, df in seen.items()}


def _vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    return {t: c * idf.get(t, 0.0) for t, c in counts.items()}


def _score(query: dict[str, float], doc: dict[str, float]) -> float:
    """Cosine similarity between two sparse weighted vectors."""
    if not query or not doc:
        return 0.0
    shared = query.keys() & doc.keys()
    if not shared:
        return 0.0
    dot = sum(query[t] * doc[t] for t in shared)
    norm = math.sqrt(sum(v * v for v in query.values())) * math.sqrt(
        sum(v * v for v in doc.values())
    )
    return dot / norm if norm else 0.0


def _retrieve(
    question: str, docs: list[tuple[int, str]], k: int = TOP_K
) -> list[dict[str, Any]]:
    """Recall for *question*: the ``k`` most relevant items, then any later item
    that revises one of them.

    Two steps, both auditable:

    1. rank by IDF-weighted cosine, ties breaking towards the **newer** row;
    2. extend forward — for each hit, pull in a later item that is talking about
       the same thing (``SUPERSEDE_SIMILARITY``), so a correction cannot be
       missed just because it is worded differently from what it corrects.

    Step 2 is bounded on both sides: a revision must clear ``MIN_SCORE`` against
    the *query* as well, and each hit contributes at most
    ``MAX_REVISIONS_PER_HIT``. The two similarities are different things and stay
    separate in the result — ``query_score`` is relevance to the question,
    ``revision_similarity`` is how much the revision looks like what it revises.
    """
    tokenised = {row_id: _tokens(text) for row_id, text in docs}
    idf = _idf(list(tokenised.values()))
    vectors = {row_id: _vector(t, idf) for row_id, t in tokenised.items()}
    query = _vector(_tokens(question), idf)
    query_scores = {
        row_id: round(_score(query, vectors[row_id]), 4) for row_id in tokenised
    }

    ranked = sorted(
        (row_id for row_id in tokenised if query_scores[row_id] >= MIN_SCORE),
        key=lambda row_id: (query_scores[row_id], row_id),
        reverse=True,
    )
    hits: list[dict[str, Any]] = [
        {
            "row": row_id,
            "query_score": query_scores[row_id],
            "revises": None,
            "revision_similarity": None,
        }
        for row_id in ranked[:k]
    ]

    seen = {hit["row"] for hit in hits}
    for hit_row in list(seen):
        candidates = []
        for later in sorted(tokenised):
            if later <= hit_row or later in seen:
                continue
            if query_scores[later] < MIN_SCORE:
                continue  # a revision has to answer the question too
            similarity = round(_score(vectors[hit_row], vectors[later]), 4)
            if similarity >= SUPERSEDE_SIMILARITY:
                candidates.append((later, similarity))
        candidates.sort(key=lambda c: (-c[1], c[0]))
        for later, similarity in candidates[:MAX_REVISIONS_PER_HIT]:
            seen.add(later)
            hits.append(
                {
                    "row": later,
                    "query_score": query_scores[later],
                    "revises": hit_row,
                    "revision_similarity": similarity,
                }
            )
    return hits


def _facts_present(text: str, facts: tuple[str, ...]) -> list[str]:
    """Facts whose every word appears in *text*. Order-free, case-insensitive."""
    words = set(_tokens(text))
    return [fact for fact in facts if set(_tokens(fact)) <= words]


# ---------------------------------------------------------------------------
# Corpora
# ---------------------------------------------------------------------------


def _snapshot_rows(snapshot: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    """Session rows from the capture, with every malformed shape reported as a
    ``ParityError`` rather than an ``AttributeError`` traceback at the CLI."""
    rows = snapshot.get("agent_messages")
    if not isinstance(rows, list):
        raise ParityError(
            "Snapshot is missing a list of 'agent_messages' — is this a "
            "session_snapshot.json produced by generate_session.py?"
        )
    selected = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ParityError(f"agent_messages[{index}] is not an object")
        if row.get("session_id") != session_id:
            continue
        try:
            row_id = int(row["id"])
        except (KeyError, TypeError, ValueError):
            raise ParityError(f"agent_messages[{index}] has no usable integer 'id'")
        raw = row.get("message_data")
        if not isinstance(raw, str):
            raise ParityError(
                f"agent_messages:{row_id} message_data is "
                f"{type(raw).__name__}, expected a JSON string"
            )
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ParityError(
                f"agent_messages:{row_id} message_data is not valid JSON ({exc})"
            )
        selected.append({"id": row_id, "payload": payload})
    if not selected:
        raise ParityError(f"Snapshot has no rows for session {session_id!r}")
    return selected


def _raw_text(payload: Any) -> str:
    """Human-readable text of one raw Responses item.

    Independent of the adapter on purpose: the "before" side must not inherit
    the adapter's own extraction choices.
    """
    if not isinstance(payload, dict):
        return ""
    parts: list[str] = []
    content = payload.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        parts.extend(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    for key in ("name", "arguments", "output"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts).strip()


def question_rows(snapshot: dict[str, Any], session_id: str) -> set[int]:
    """Rows that only *ask* something, so they can never count as an answer.

    A user turn whose text ends in '?' states no fact. Left in the corpus it
    lets a query "succeed" by retrieving its own question back — which proves
    nothing about whether the answer survived the migration.
    """
    asked = set()
    for row in _snapshot_rows(snapshot, session_id):
        payload = row["payload"]
        if not isinstance(payload, dict) or payload.get("role") != "user":
            continue
        if _raw_text(payload).strip().endswith("?"):
            asked.add(row["id"])
    return asked


def before_corpus(
    snapshot: dict[str, Any], session_id: str, exclude: set[int]
) -> list[tuple[int, str]]:
    """The raw SDK session: ``(row id, text)`` for every answer-bearing item."""
    docs = []
    for row in _snapshot_rows(snapshot, session_id):
        if row["id"] in exclude:
            continue
        text = _raw_text(row["payload"])
        if text:
            docs.append((row["id"], text))
    if not docs:
        raise ParityError(f"No source text found for session {session_id!r}")
    return docs


def after_corpus(bundle: Path, exclude: set[int]) -> list[tuple[int, str]]:
    """The memories Memanto would store, via its own loader and mapper.

    The same question-only rows are dropped here, so both sides are judged on
    answer-bearing evidence alone.
    """
    try:
        from memanto.cli.migrate.mappers import map_okf
        from memanto.cli.migrate.okf_loader import load_okf_bundle
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ParityError(
            "memanto must be importable to build the migrated corpus "
            f"(pip install -e ../../..): {exc}"
        )

    try:
        mapped = map_okf(load_okf_bundle(bundle))
    except FileNotFoundError as exc:
        raise ParityError(f"OKF bundle not readable: {exc}")

    docs = []
    for row in mapped:
        ref = str(row.get("source_ref") or "")
        content = str(row.get("content") or "")
        if not ref or not content:
            continue
        try:
            row_id = int(ref.rsplit("/", 1)[-1])
        except ValueError:
            raise ParityError(
                f"Mapped memory has an unreadable source_ref {ref!r}: expected it "
                "to end in the source row id"
            )
        if row_id not in exclude:
            docs.append((row_id, content))
    if not docs:
        raise ParityError(f"No memories mapped from {bundle}")
    return docs


def concept_index(report: dict[str, Any]) -> dict[int, str]:
    """``row id -> OKF document``, so a merged tool call + result is one concept."""
    entries = report.get("mapped")
    if not isinstance(entries, list):
        raise ParityError(
            "Adapter report is missing a list of 'mapped' entries — is this an "
            "adapter-report.json produced by okf_adapter.py?"
        )
    index: dict[int, str] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ParityError(f"Adapter report mapped[{position}] is not an object")
        document = entry.get("okf_document")
        items = entry.get("source_items")
        if not isinstance(document, str) or not isinstance(items, list):
            raise ParityError(
                f"Adapter report mapped[{position}] needs 'okf_document' and a "
                "list of 'source_items'"
            )
        for item in items:
            try:
                index[int(str(item).split(":")[-1])] = document
            except ValueError:
                raise ParityError(
                    f"Adapter report mapped[{position}] has an unreadable source "
                    f"item {item!r}: expected '<table>:<row id>'"
                )
    return index


# ---------------------------------------------------------------------------
# Parity
# ---------------------------------------------------------------------------


def _evaluate_side(
    query: Query,
    corpus: list[tuple[int, str]],
    concepts: dict[int, str],
) -> dict[str, Any]:
    """Retrieve for one corpus and grade the evidence it returns."""
    text_by_row = dict(corpus)
    hits = _retrieve(query.question, corpus)

    covered: list[str] = []
    answer_rows: list[int] = []
    stale_rows: list[int] = []
    for hit in hits:
        row_id = hit["row"]
        text = text_by_row[row_id]
        found = _facts_present(text, query.expects)
        if found:
            answer_rows.append(row_id)
            covered.extend(f for f in found if f not in covered)
        elif _facts_present(text, query.superseded):
            stale_rows.append(row_id)

    coverage = len(covered) / len(query.expects) if query.expects else 0.0
    # Where a correction conflicts with an earlier answer, the newer evidence
    # has to be the one carrying the facts.
    correction_wins = not stale_rows or (
        bool(answer_rows) and max(answer_rows) > max(stale_rows)
    )
    return {
        "retrieved": [
            {
                "source_item": f"agent_messages:{hit['row']}",
                # Relevance to the question...
                "query_score": hit["query_score"],
                # ...kept apart from "this later item revises that hit".
                "revises": (
                    f"agent_messages:{hit['revises']}"
                    if hit["revises"] is not None
                    else None
                ),
                "revision_similarity": hit["revision_similarity"],
            }
            for hit in hits
        ],
        "retrieved_count": len(hits),
        "corpus_size": len(corpus),
        "answer_items": [f"agent_messages:{row}" for row in answer_rows],
        "answer_concepts": sorted(
            {concepts[row] for row in answer_rows if row in concepts}
        ),
        "superseded_items": [f"agent_messages:{row}" for row in stale_rows],
        "facts_expected": list(query.expects),
        "facts_found": covered,
        "fact_coverage": round(coverage, 4),
        "meets_coverage": coverage >= FACT_COVERAGE,
        "correction_wins": correction_wins,
    }


def run_parity(
    *,
    snapshot: dict[str, Any],
    bundle: Path,
    report: dict[str, Any],
    session_id: str = SESSION_ID,
    queries: tuple[Query, ...] | None = None,
) -> dict[str, Any]:
    """Grade every query on both corpora and return the parity report."""
    queries = tuple(queries or QUERIES)
    excluded = question_rows(snapshot, session_id)
    before = before_corpus(snapshot, session_id, excluded)
    after = after_corpus(bundle, excluded)
    concepts = concept_index(report)

    results = []
    for query in queries:
        before_side = _evaluate_side(query, before, concepts)
        after_side = _evaluate_side(query, after, concepts)
        # Equivalent evidence is fine — the merged tool record and the user's own
        # statement are the same concept — so compare concepts, not row ids.
        shared = sorted(
            set(before_side["answer_concepts"]) & set(after_side["answer_concepts"])
        )
        results.append(
            {
                "question": query.question,
                "expected_facts": list(query.expects),
                "superseded_facts": list(query.superseded),
                "before": before_side,
                "after": after_side,
                "shared_answer_concepts": shared,
                "passed": (
                    before_side["meets_coverage"]
                    and after_side["meets_coverage"]
                    and before_side["correction_wins"]
                    and after_side["correction_wins"]
                    and bool(shared)
                ),
            }
        )

    passed = sum(1 for r in results if r["passed"])
    parity = passed / len(results) if results else 0.0
    return {
        "_comment": (
            "Offline before/after query parity. The 'before' corpus is the raw "
            "OpenAI Agents SDK session capture; the 'after' corpus is the "
            "memories Memanto's own load_okf_bundle + map_okf produce from the "
            "committed OKF bundle. Rows that only ask a question are excluded "
            "from both, so a query can never 'pass' by retrieving itself. Each "
            "query is graded against facts copied from the scripted run, and "
            "every query must pass. This measures preservation and "
            "retrievability, NOT live Moorcheh recall — no cloud call is made "
            "or simulated."
        ),
        "method": (
            f"idf-weighted cosine over word tokens, top-{TOP_K} recall "
            "(newer evidence wins ties), extended by at most "
            f"{MAX_REVISIONS_PER_HIT} still-relevant revision per hit, graded by "
            "expected-fact coverage"
        ),
        "measures": "preservation / query parity (offline)",
        "not_measured": "live Moorcheh recall quality",
        "session_id": session_id,
        "excluded_question_rows": [f"agent_messages:{row}" for row in sorted(excluded)],
        "corpus_sizes": {"before_items": len(before), "after_memories": len(after)},
        "threshold": PARITY_THRESHOLD,
        "fact_coverage_threshold": FACT_COVERAGE,
        "questions": len(results),
        "passed": passed,
        "parity": round(parity, 4),
        "meets_threshold": parity >= PARITY_THRESHOLD,
        "results": results,
    }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ParityError(f"{label} not found: {path}")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParityError(f"{label} is not valid JSON ({path}): {exc}")
    if not isinstance(loaded, dict):
        raise ParityError(f"{label} must be a JSON object: {path}")
    return loaded


def load_parity_report(
    snapshot_path: Path = SNAPSHOT,
    bundle: Path = BUNDLE,
    report_path: Path = REPORT,
    session_id: str = SESSION_ID,
) -> dict[str, Any]:
    return run_parity(
        snapshot=_read_json(snapshot_path, "Source snapshot"),
        bundle=bundle,
        report=_read_json(report_path, "Adapter report"),
        session_id=session_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline before/after query parity.")
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--session", default=SESSION_ID, help="Session id to check parity for."
    )
    parser.add_argument("--json", type=Path, help="Write the parity report here.")
    args = parser.parse_args(argv)

    try:
        parity = load_parity_report(
            args.snapshot, args.bundle, args.report, args.session
        )
    except ParityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Before/after query parity — offline, no live recall")
    print(
        f"  corpora: {parity['corpus_sizes']['before_items']} raw SDK items -> "
        f"{parity['corpus_sizes']['after_memories']} Memanto memories"
    )
    print(f"  method : {parity['method']}")
    print(
        "  excluded question-only rows: "
        f"{', '.join(parity['excluded_question_rows']) or 'none'}\n"
    )
    for result in parity["results"]:
        mark = "ok  " if result["passed"] else "FAIL"
        before, after = result["before"], result["after"]
        print(f"  [{mark}] {result['question']}")
        print(f"         expects {', '.join(result['expected_facts'])}")
        print(
            f"         before {', '.join(before['answer_items']) or 'no answer'} "
            f"({before['fact_coverage']:.0%} of "
            f"{before['retrieved_count']}/{before['corpus_size']} recalled) -> "
            f"after {', '.join(after['answer_items']) or 'no answer'} "
            f"({after['fact_coverage']:.0%} of "
            f"{after['retrieved_count']}/{after['corpus_size']} recalled)"
        )
        if result["superseded_facts"]:
            stale = ", ".join(before["superseded_items"] + after["superseded_items"])
            print(
                f"         correction beats stale evidence "
                f"[{stale or 'none retrieved'}]: "
                f"{before['correction_wins'] and after['correction_wins']}"
            )
    print(
        f"\nparity {parity['parity']:.0%} "
        f"({parity['passed']}/{parity['questions']} questions), "
        f"required {parity['threshold']:.0%} with "
        f"{parity['fact_coverage_threshold']:.0%} fact coverage each: "
        f"{'PASS' if parity['meets_threshold'] else 'FAIL'}"
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(parity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"report {args.json}")

    return 0 if parity["meets_threshold"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
