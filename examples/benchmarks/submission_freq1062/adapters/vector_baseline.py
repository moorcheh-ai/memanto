"""VectorBaseline — pure embedding + cosine similarity. No LLM gate.

The simplest possible memory system: embed every turn, search via
cosine similarity.  Serves as the minimal baseline for comparison.
"""

from __future__ import annotations

import time
import uuid

import numpy as np
from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class VectorBaselineAdapter(MemorySystem):
    """In-memory vector store using cluster embeddings + cosine similarity.

    Uses the user's private ML cluster (no rate limits).  Embedding dim = 384
    (all-MiniLM-L6-v2).
    """

    def __init__(self, embed_model: str = "", pacing: float = 0.0):
        self.embed_model = embed_model  # unused, cluster handles it
        self.pacing = pacing
        self._stores: dict[str, tuple[list[DialogueTurn], list[np.ndarray]]] = {}

    def name(self) -> str:
        return "vector-baseline"

    def setup(self) -> None:
        """Nothing to set up — embeddings are fetched live via providers."""
        pass

    def teardown(self) -> None:
        self._stores.clear()

    # ------------------------------------------------------------------
    # store / search
    # ------------------------------------------------------------------

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        from providers import local_embed

        if namespace not in self._stores:
            self._stores[namespace] = ([], [])

        turn_list, emb_list = self._stores[namespace]

        # No rate limits on cluster — batch everything aggressively
        batch_size = 50
        for i in range(0, len(turns), batch_size):
            batch = turns[i : i + batch_size]
            texts = [t.text for t in batch]
            embs = local_embed(texts)
            if isinstance(embs, list) and len(embs) == len(batch):
                for t, e in zip(batch, embs, strict=True):
                    turn_list.append(t)
                    emb_list.append(np.array(e, dtype=np.float32))
            if self.pacing:
                time.sleep(self.pacing)

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]:
        from providers import local_embed

        if namespace not in self._stores:
            return []

        turn_list, emb_list = self._stores[namespace]
        if not turn_list:
            return []

        query_emb = np.array(
            local_embed(query),
            dtype=np.float32,
        )

        # Compute cosine similarity
        embs = np.stack(emb_list)  # (N, dim)
        dots = embs @ query_emb
        norms = np.linalg.norm(embs, axis=1) * np.linalg.norm(query_emb)
        scores = dots / np.maximum(norms, 1e-12)

        # Top-K
        top_idx = np.argsort(scores)[-k:][::-1]
        items = []
        for idx in top_idx:
            items.append(
                RetrievedItem(
                    dia_id=turn_list[idx].dia_id,
                    session_id=turn_list[idx].session_id,
                    text=turn_list[idx].text,
                    score=float(scores[idx]),
                )
            )
        return items

    # ------------------------------------------------------------------
    # dry-run / cleanup
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
        from providers import check_keys

        if not check_keys("CLUSTER_API_KEY"):
            pass

        ns = f"dry-{uuid.uuid4().hex[:6]}"
        test_turn = DialogueTurn(
            dia_id="DRY:1",
            speaker="tester",
            text="The sky is cerulean today.",
            session_id="dry-session",
        )
        try:
            print("  [dry-run] setup …")
            self.setup()
            print("    ✓ setup")

            print("  [dry-run] store …")
            self.store_turns([test_turn], ns)
            print("    ✓ store")

            print("  [dry-run] search …")
            results = self.search("What color is the sky?", ns, k=3)
            found = any("cerulean" in r.text.lower() for r in results)
            print(
                f"    ✓ retrieved {len(results)} results, "
                f"contains-answer={'yes' if found else 'NO'}"
            )
            if not found:
                return False

            print("  [dry-run] teardown …")
            self.teardown()
            print("    ✓ teardown")
            return True
        except Exception as e:
            print(f"    ✗  dry-run failed: {e}")
            return False

    def cleanup(self) -> None:
        self._stores.clear()
        print("    vector-baseline cleanup: cleared in-memory stores")
