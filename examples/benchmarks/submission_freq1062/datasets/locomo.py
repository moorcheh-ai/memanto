"""LoCoMo dataset — turn-level evidence, 10 conversations, 1986 QA pairs.

MIT-licensed (SNAP Research).  Each QA pair includes ``evidence``
annotations like ``["D1:3", "D2:8"]`` that point to exact dialogue
turns.  Scoring is deterministic — no LLM judge needed.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Literal

from interfaces import (
    BenchmarkDataset,
    Conversation,
    Dataset,
    DialogueTurn,
    EvidenceSpan,
    QAPair,
    RetrievedItem,
    _default_compute_scores,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCOMO_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
)
LONGMEMEVAL_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/"
)
LONGMEMEVAL_FILES = {
    "oracle": "longmemeval_oracle.json",
    "s": "longmemeval_s_cleaned.json",
}

CACHE_DIR = Path.home() / ".cache" / "memanto-benchmark"
CATEGORY_NAMES = {
    1: "factual",
    2: "temporal",
    3: "inferential",
    4: "multi-hop",
    5: "adversarial",
}
LONGMEMEVAL_CATEGORIES = {
    "single-session-user": "single-session-user",
    "single-session-assistant": "single-session-assistant",
    "single-session-preference": "single-session-preference",
    "multi-session": "multi-session",
    "temporal-reasoning": "temporal-reasoning",
    "knowledge-update": "knowledge-update",
}


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------


def _cached_download(url: str, cache_name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / cache_name
    if not dest.exists():
        print(f"  Downloading {url[:80]}...")
        urllib.request.urlretrieve(url, dest)
    return dest


# ---------------------------------------------------------------------------
# Dataset class
# ---------------------------------------------------------------------------


class LoCoMoDataset(Dataset):
    name = "LoCoMo"
    description = (
        "10 multi-session conversations, 1986 QA pairs with turn-level "
        "evidence annotations across 5 categories."
    )

    def load(
        self,
        limit: int | None = None,
        split: Literal["oracle", "s"] | None = None,
        max_turns_per_conv: int | None = None,
    ) -> BenchmarkDataset:
        """Load LoCoMo or LongMemEval.

        If ``split`` is provided, loads LongMemEval instead.
        """
        if split:
            return self._load_longmemeval(split, limit, max_turns_per_conv)
        return self._load_locomo(limit, max_turns_per_conv)

    # ---- LoCoMo -----------------------------------------------------------

    def _load_locomo(
        self, limit: int | None, max_turns_per_conv: int | None = None
    ) -> BenchmarkDataset:
        path = _cached_download(LOCOMO_URL, "locomo10.json")
        with open(path) as f:
            raw = json.load(f)

        conversations = [
            self._parse_locomo_conv(c) for c in (raw[:limit] if limit else raw)
        ]
        return BenchmarkDataset(
            name=self.name,
            conversations=conversations,
            description=self.description,
        )

    def _parse_locomo_conv(
        self, raw: dict, max_turns: int | None = None
    ) -> Conversation:
        sample_id = raw.get("sample_id", "unknown")
        conv_data = raw.get("conversation", {})

        turns: list[DialogueTurn] = []
        snums = sorted(
            int(k.split("_")[1])
            for k in conv_data
            if k.startswith("session_") and not k.endswith("_date_time")
        )
        for sn in snums:
            sk = f"session_{sn}"
            for t in conv_data.get(sk, []):
                turns.append(
                    DialogueTurn(
                        dia_id=t.get("dia_id", f"D{sn}:{len(turns) + 1}"),
                        speaker=t.get("speaker", "unknown"),
                        text=t.get("text", ""),
                        session_id=sk,
                    )
                )

        if max_turns:
            turns = turns[:max_turns]

        qa_pairs: list[QAPair] = []
        for qa_raw in raw.get("qa", []):
            evidence = []
            for ev in qa_raw.get("evidence", []):
                parts = ev.split(":")
                snum = parts[0][1:] if parts[0].startswith("D") else parts[0]
                evidence.append(
                    EvidenceSpan(
                        session_id=f"session_{snum}",
                        turn_ids=[ev],
                    )
                )
            qa_pairs.append(
                QAPair(
                    question=qa_raw.get("question", ""),
                    answer=qa_raw.get("answer", ""),
                    category=CATEGORY_NAMES.get(qa_raw.get("category", 0), "unknown"),
                    category_id=qa_raw.get("category", 0),
                    evidence=evidence,
                )
            )
        return Conversation(sample_id=sample_id, turns=turns, qa_pairs=qa_pairs)

    # ---- LongMemEval -------------------------------------------------------

    def _load_longmemeval(
        self,
        split: str,
        limit: int | None,
        max_turns_per_conv: int | None = None,
    ) -> BenchmarkDataset:
        url = LONGMEMEVAL_URL + LONGMEMEVAL_FILES[split]
        path = _cached_download(url, f"longmemeval_{split}.json")
        with open(path) as f:
            raw = json.load(f)

        conversations = [
            self._parse_lme_item(item) for item in (raw[:limit] if limit else raw)
        ]
        return BenchmarkDataset(
            name=f"LongMemEval-{split}",
            conversations=conversations,
            description=f"LongMemEval {split} — "
            f"{len(raw)} questions, session-level evidence.",
        )

    def _parse_lme_item(self, item: dict) -> Conversation:
        qid = item.get("question_id", "unknown")
        answer_sids = set(item.get("answer_session_ids", []))

        turns: list[DialogueTurn] = []
        for sid, sess in zip(
            item.get("haystack_session_ids", []),
            item.get("haystack_sessions", []),
            strict=True,
        ):
            for ti, msg in enumerate(sess):
                turns.append(
                    DialogueTurn(
                        dia_id=f"{sid}_{ti}",
                        speaker=msg.get("role", "unknown"),
                        text=msg.get("content", ""),
                        session_id=sid,
                    )
                )

        evidence = [EvidenceSpan(session_id=s, turn_ids=[]) for s in answer_sids]
        qa = QAPair(
            question=item.get("question", ""),
            answer=str(item.get("answer", "")),
            category=item.get("question_type", "unknown"),
            category_id=item.get("question_type", "unknown"),
            evidence=evidence,
            question_id=qid,
        )
        return Conversation(sample_id=qid, turns=turns, qa_pairs=[qa])

    # ---- Metrics -----------------------------------------------------------

    def compute_metrics(
        self,
        retrieved: list[RetrievedItem],
        qa: QAPair,
        k: int = 10,
        judge_fn: callable | None = None,
    ) -> tuple[float, float, bool, int, dict]:
        return (*_default_compute_scores(retrieved, qa, k), {})

    # ---- Dry-run -----------------------------------------------------------

    def dry_run(self) -> bool:
        print("  [dry-run] loading 1 conversation …")
        try:
            ds = self.load(limit=1)
            print(
                f"    ✓  {len(ds.conversations)} conv, "
                f"{ds.total_turns} turns, {ds.total_qa_pairs} QA"
            )
        except Exception as e:
            print(f"    ✗  load failed: {e}")
            return False

        conv = ds.conversations[0]
        if not conv.qa_pairs or not conv.turns:
            print("    ✗  empty conversation")
            return False

        # Spot-check first QA pair
        qa = conv.qa_pairs[0]
        if not qa.evidence:
            print("    ✗  no evidence annotations")
            return False

        # Verify evidence maps to real turns
        for ev in qa.evidence:
            for tid in ev.turn_ids:
                found = [t for t in conv.turns if t.dia_id == tid]
                if not found:
                    print(f"    ✗  evidence {tid} not in turns")
                    return False

        # Test compute_metrics with a simulated perfect hit
        dummy = [
            RetrievedItem(
                dia_id=tid,
                session_id=qa.evidence[0].session_id,
                text="ok",
                score=1.0,
            )
            for ev in qa.evidence
            for tid in ev.turn_ids
        ]
        recall, precision, _, _, _ = self.compute_metrics(dummy, qa)
        if recall != 1.0:
            print(f"    ✗  perfect hit recall={recall} (expected 1.0)")
            return False

        print("    ✓  evidence mapping OK, metrics compute correctly")
        return True
