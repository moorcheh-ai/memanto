"""Tests for the validation harness + extraction boundary guards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from adapters.extract import extract_memories  # noqa: E402
from validate_roundtrip import offline_parity  # noqa: E402


def test_extract_rejects_negative_caps():
    conv = [{"id": "c1", "title": "t", "source": "chatgpt",
             "turns": [{"role": "user", "text": "I prefer Postgres.", "ts": 1}]}]
    with pytest.raises(ValueError):
        extract_memories(conv, max_per_type=-1)
    with pytest.raises(ValueError):
        extract_memories(conv, max_total=-5)
    # zero and positive limits remain valid
    r = extract_memories(conv, max_per_type=0, max_total=0)
    assert r["memories"] == []


def test_offline_parity_does_not_aggregate_across_memories(tmp_path):
    """Tokens distributed across separate memories must not satisfy the
    threshold: an answer is recallable only if a SINGLE memory carries >= 50%."""
    memories_dir = tmp_path / "memories" / "fact"
    memories_dir.mkdir(parents=True)
    (memories_dir / "a.md").write_text("alpha beta gamma", encoding="utf-8")
    (memories_dir / "b.md").write_text("delta epsilon zeta", encoding="utf-8")

    # 7-token answer split 3+3 across two memories: per-file best = 3/7 < 0.5
    golden = [{"q": "What is the answer?", "a": "alpha beta gamma delta epsilon zeta eta", "type": "fact"}]
    result = offline_parity(golden, tmp_path)
    assert result["recall_hits"] == 0, "distributed tokens must not count as a hit"
    assert result["recall"] == 0.0

    # the same answer fully present in ONE memory is a hit
    (memories_dir / "c.md").write_text(
        "alpha beta gamma delta epsilon zeta eta", encoding="utf-8")
    result2 = offline_parity(golden, tmp_path)
    assert result2["recall_hits"] == 1
