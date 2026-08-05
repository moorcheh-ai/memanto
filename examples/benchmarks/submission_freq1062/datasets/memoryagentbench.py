"""MemoryAgentBench dataset (ICLR 2026, MIT license).

No turn-level evidence — scoring uses an LLM judge to compare retrieved
text against the ground-truth answer.  Default judge: Groq llama-3.1-8b-instant.

Splits:
    Accurate_Retrieval  — 2000 QA across EventQA, LongMemEval, RULER
    Conflict_Resolution — 800 QA across FactConsolidation variants
                          (contradiction / updated-information scenarios)
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Literal

from interfaces import (
    BenchmarkDataset,
    Conversation,
    Dataset,
    DialogueTurn,
    QAPair,
    RetrievedItem,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HF_REPO = "ai-hyz/MemoryAgentBench"
CACHE_DIR = Path.home() / ".cache" / "memanto-benchmark"

SPLIT_FILES: dict[str, str] = {
    "Accurate_Retrieval": "data/Accurate_Retrieval-00000-of-00001.parquet",
    "Conflict_Resolution": "data/Conflict_Resolution-00000-of-00001.parquet",
}

SPLIT_DESCRIPTIONS = {
    "Accurate_Retrieval": (
        "2000 QA across EventQA, LongMemEval, RULER. "
        "Tests accurate fact retrieval from long contexts."
    ),
    "Conflict_Resolution": (
        "800 QA across FactConsolidation variants. "
        "Tests resolving conflicting/updated information."
    ),
}

# ---------------------------------------------------------------------------
# Dataset class
# ---------------------------------------------------------------------------


class MemoryAgentBenchDataset(Dataset):
    name = "MemoryAgentBench"
    description = (
        "Long-context retrieval benchmark with 100 QA per row. "
        "No turn-level evidence — scored via LLM judge."
    )

    def __init__(
        self,
        judge_model: str = "llama-3.1-8b-instant",
        judge_api_key: str = "",
    ):
        self.judge_model = judge_model
        self.judge_api_key = judge_api_key

    # ---- Loading -----------------------------------------------------------

    def load(
        self,
        limit: int | None = None,
        split: Literal[
            "Accurate_Retrieval", "Conflict_Resolution"
        ] = "Conflict_Resolution",
        max_turns_per_conv: int | None = None,
    ) -> BenchmarkDataset:
        import pyarrow.parquet as pq

        path = self._download_parquet(split)
        table = pq.read_table(str(path))
        n = min(table.num_rows, limit) if limit else table.num_rows

        conversations: list[Conversation] = []
        for i in range(n):
            row = table.slice(i, 1)
            source, qa_pairs, ctx = self._parse_row(row)
            conversations.append(self._make_conv(ctx, qa_pairs, source, i))

        qa_total = sum(len(c.qa_pairs) for c in conversations)
        return BenchmarkDataset(
            name=f"MemoryAgentBench-{split}",
            conversations=conversations,
            description=f"{SPLIT_DESCRIPTIONS.get(split, '')} "
            f"{qa_total} total QA pairs.",
        )

    def _download_parquet(self, split: str) -> Path:
        url = (
            f"https://huggingface.co/datasets/{HF_REPO}"
            f"/resolve/main/{SPLIT_FILES[split]}"
        )
        dest = CACHE_DIR / f"mab_{split}.parquet"
        if dest.exists():
            return dest
        print(f"  Downloading MemoryAgentBench {split}...")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        return dest

    def _parse_row(self, row) -> tuple[str, list[QAPair], str]:
        meta = row.column("metadata")[0].as_py()
        questions = row.column("questions")[0].as_py()
        answers_raw = row.column("answers")[0].as_py()
        ctx = row.column("context")[0].as_py() or ""

        source = meta.get("source", "unknown")
        qids = meta.get("qa_pair_ids") or []

        qa_pairs = []
        for j, q in enumerate(questions):
            a = answers_raw[j] if j < len(answers_raw) else [""]
            ans = a[0] if isinstance(a, list) else str(a)
            qa_pairs.append(
                QAPair(
                    question=str(q),
                    answer=ans,
                    category=source,
                    category_id=source,
                    question_id=qids[j] if j < len(qids) else f"{source}_{j}",
                    evidence=[],
                )
            )
        return source, qa_pairs, ctx

    def _make_conv(
        self,
        ctx: str,
        qa_pairs: list[QAPair],
        source: str,
        idx: int,
    ) -> Conversation:
        sid = f"{source}_{idx}"
        return Conversation(
            sample_id=sid,
            turns=[
                DialogueTurn(
                    dia_id=f"{sid}_ctx",
                    speaker="user",
                    text=ctx,
                    session_id=sid,
                )
            ],
            qa_pairs=qa_pairs,
        )

    # ---- Metrics (LLM judge based) ----------------------------------------

    def compute_metrics(
        self,
        retrieved: list[RetrievedItem],
        qa: QAPair,
        k: int = 10,
        judge_fn: callable | None = None,
    ) -> tuple[float, float, bool, int, dict]:
        """Score via Groq LLM judge (self-contained, no external import needed)."""
        texts = [r.text for r in retrieved[:k]]

        if judge_fn is None:
            # Default: use Groq judge built into providers
            from providers import groq_judge as _judge

            def _judge_fn(q, a, texts):
                return _judge(
                    q, a, texts, model=self.judge_model, api_key=self.judge_api_key
                )

            judge_fn = _judge_fn

        try:
            correct = judge_fn(qa.question, qa.answer, texts)
        except Exception as e:
            print(f"    judge error: {e}")
            correct = False

        recall = 1.0 if correct else 0.0
        precision = recall
        has_stale = False
        stale_count = 0
        extra = {"judge_correct": correct}
        return recall, precision, has_stale, stale_count, extra

    # ---- Dry-run -----------------------------------------------------------

    def dry_run(self) -> bool:
        print("  [dry-run] loading 1 row …")
        try:
            ds = self.load(limit=1, split="Conflict_Resolution")
            print(f"    ✓  {len(ds.conversations)} rows, {ds.total_qa_pairs} QA pairs")
        except Exception as e:
            print(f"    ✗  load failed: {e}")
            return False

        conv = ds.conversations[0]
        if not conv.qa_pairs:
            print("    ✗  no QA pairs")
            return False

        qa = conv.qa_pairs[0]
        print(f"    test QA: {qa.question[:80]}")

        # Test compute_metrics without judge (returns False)
        dummy = [
            RetrievedItem(
                dia_id="test",
                session_id="test",
                text=qa.answer,
                score=1.0,
            )
        ]
        recall, prec, _, _, extra = self.compute_metrics(dummy, qa)
        print(f"    ✓  compute_metrics OK (recall={recall})")

        # Test judge if GROQ_API_KEY is available
        if os.environ.get("GROQ_API_KEY"):
            from providers import groq_judge

            try:
                correct = groq_judge(qa.question, qa.answer, [qa.answer])
                print(
                    f"    ✓  judge returns correct={'yes' if correct else 'NO'} "
                    f"(for trivial match)"
                )
            except Exception as e:
                print(f"    ✗  judge failed: {e}")
                return False

        return True
