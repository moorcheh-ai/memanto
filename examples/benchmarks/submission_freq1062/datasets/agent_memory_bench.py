"""AgentMemoryBench — 100-turn conversation with hidden_facts and 20 QA pairs.

Each turn has ``hidden_facts`` — what a perfect memory system should extract.
78/100 turns are filler (noise), making this a good test of filler rejection.

Evidence annotations are derived by matching hidden_facts against each
question's ground_truth answer via substring matching on the normalized
answer text.  This gives deterministic turn-level evidence like LoCoMo.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

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

CACHE_DIR = Path.home() / ".cache" / "memanto-benchmark"
REPO = "kushalicious/agent-memory-benchmark"
BASE_URL = f"https://huggingface.co/datasets/{REPO}/resolve/main"


class AgentMemoryBenchDataset(Dataset):
    name = "AgentMemoryBench"
    description = (
        "100-turn single-session conversation with 22 info turns, "
        "78 filler turns, and 20 factoid QA pairs.  hidden_facts per "
        "turn provide turn-level evidence annotations."
    )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(
        self,
        limit: int | None = None,
        **kwargs,
    ) -> BenchmarkDataset:
        conv_path = self._cached("data/conversation.json")
        qa_path = self._cached("eval/questions.json")

        with open(conv_path) as f:
            raw_conv = json.load(f)
        with open(qa_path) as f:
            raw_qs = json.load(f)

        conversations = [self._build_conversation(raw_conv, raw_qs)]
        return BenchmarkDataset(
            name=self.name,
            conversations=conversations,
            description=self.description,
        )

    def _cached(self, filename: str) -> Path:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dest = CACHE_DIR / f"amb_{filename.replace('/', '_')}"
        if not dest.exists():
            url = f"{BASE_URL}/{filename}"
            print(f"  Downloading {url[:80]}...")
            urllib.request.urlretrieve(url, dest)
        return dest

    def _build_conversation(
        self,
        raw_conv: list[dict],
        raw_qs: list[dict],
    ) -> Conversation:
        # Build turns
        turns: list[DialogueTurn] = []
        for t in raw_conv:
            turns.append(
                DialogueTurn(
                    dia_id=str(t["turn"]),
                    speaker=t["role"],
                    text=t["content"],
                    session_id="session_1",
                )
            )

        # Build hidden_facts lookup: turn_num → set of facts
        fact_by_turn: dict[int, list[str]] = {}
        for t in raw_conv:
            hf = t.get("hidden_facts", [])
            if hf:
                fact_by_turn[t["turn"]] = hf

        # Build QA pairs with evidence derived from hidden_facts
        qa_pairs: list[QAPair] = []
        for q in raw_qs:
            qid = q["question_id"]
            gt = q["ground_truth"]
            question = q["question"]

            # Find which turns have hidden_facts that contain this answer
            evidence_turns: list[str] = []
            for tnum, facts in fact_by_turn.items():
                for fact in facts:
                    if self._answer_in_fact(gt, fact):
                        evidence_turns.append(str(tnum))
                        break

            evidence = [
                EvidenceSpan(
                    session_id="session_1",
                    turn_ids=[tid],
                )
                for tid in evidence_turns
            ]

            qa_pairs.append(
                QAPair(
                    question=question,
                    answer=gt,
                    category="factual",
                    category_id="factual",
                    evidence=evidence,
                    question_id=qid,
                )
            )

        return Conversation(
            sample_id="amb_1",
            turns=turns,
            qa_pairs=qa_pairs,
        )

    @staticmethod
    def _answer_in_fact(answer: str, fact: str) -> bool:
        """Check if the answer text appears in a hidden_fact."""
        # Normalize both
        a_clean = answer.lower().strip().rstrip(".")
        f_clean = fact.lower().strip()
        return a_clean in f_clean or any(
            word in f_clean
            for word in a_clean.split()
            if len(word) > 2  # skip very short words
        )

    # ------------------------------------------------------------------
    # Metrics (deterministic evidence matching — same as LoCoMo)
    # ------------------------------------------------------------------

    def compute_metrics(
        self,
        retrieved: list[RetrievedItem],
        qa: QAPair,
        k: int = 10,
        judge_fn: callable | None = None,
    ) -> tuple[float, float, bool, int, dict]:
        return (*_default_compute_scores(retrieved, qa, k), {})

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
        print("  [dry-run] loading ...")
        try:
            ds = self.load()
        except Exception as e:
            print(f"    ✗  load failed: {e}")
            return False

        if not ds.conversations:
            print("    ✗  no conversations")
            return False

        conv = ds.conversations[0]
        print(
            f"    ✓  {len(conv.turns)} turns, {len(conv.qa_pairs)} QA, "
            f"{sum(1 for t in conv.turns if 'filler' not in (t.text or '').lower())} info turns"
        )

        if not conv.qa_pairs:
            print("    ✗  no QA pairs")
            return False

        # Verify QA with evidence
        qa_with_ev = sum(1 for q in conv.qa_pairs if q.evidence)
        qa_total = len(conv.qa_pairs)
        print(f"    ✓  {qa_with_ev}/{qa_total} QA have evidence annotations")

        # Test compute_metrics with a simulated hit
        qa = conv.qa_pairs[0]
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
        recall, prec, _, _, _ = self.compute_metrics(dummy, qa)
        if recall != 1.0:
            print(f"    ✗  perfect hit recall={recall} (expected 1.0)")
            return False

        print("    ✓  compute_metrics OK (recall=1.0)")
        return True
