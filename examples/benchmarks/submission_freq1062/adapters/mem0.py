"""Mem0 adapter — local LLM + local embeddings via HTTP API server.

Uses OpenAI-compatible local API server at 127.0.0.1:8080 for both
LLM extraction (infer=True) and embedding. The ``openai_base_url``
config field IS supported by mem0's OpenAI provider.

Default models:
    LLM:      openai / Qwen2.5-7B-Instruct-Q4_K_M  (local server)
    Embedder: openai / all-MiniLM-L6-v2            (local server, 384d)
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class Mem0Adapter(MemorySystem):
    def __init__(
        self,
        llm_provider: str = "openai",
        llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M",
        embedder_provider: str = "openai",
        embedder_model: str = "all-MiniLM-L6-v2",
        embedder_dims: int = 384,
        openai_base_url: str = "http://127.0.0.1:8080/v1",
        infer: bool = False,
        pacing: float = 0.3,
        max_retries: int = 5,
    ):
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.embedder_provider = embedder_provider
        self.embedder_model = embedder_model
        self.embedder_dims = embedder_dims
        self.openai_base_url = openai_base_url
        self.infer = infer
        self.pacing = pacing
        self.max_retries = max_retries
        self._memory = None
        self._user_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def name(self) -> str:
        suffix = "-infer" if self.infer else ""
        return f"mem0{suffix}"

    # ------------------------------------------------------------------
    # setup / teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        from mem0 import Memory

        # Set env for OpenAI provider (picked up by mem0's OpenAI client)
        os.environ.setdefault("OPENAI_API_KEY", "local-key")
        os.environ.setdefault("OPENAI_BASE_URL", self.openai_base_url)

        config = {
            "llm": {
                "provider": self.llm_provider,
                "config": {
                    "model": self.llm_model,
                    "temperature": 0.1,
                    "openai_base_url": self.openai_base_url,
                },
            },
            "embedder": {
                "provider": self.embedder_provider,
                "config": {
                    "model": self.embedder_model,
                    "api_key": "local-key",
                    "openai_base_url": self.openai_base_url,
                },
            },
            "vector_store": {
                "config": {
                    "embedding_model_dims": self.embedder_dims,
                },
            },
            "version": "v1.1",
        }
        self._memory = Memory.from_config(config)

    def teardown(self) -> None:
        for user_id in self._user_ids.values():
            try:
                self._memory.delete_all(user_id=user_id)
            except Exception:
                pass
        self._user_ids.clear()

    def cleanup(self) -> None:
        import shutil

        for p in [Path.home() / ".mem0"]:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                print(f"    mem0 cleanup: removed {p}")

    # ------------------------------------------------------------------
    # store / search
    # ------------------------------------------------------------------

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        if namespace not in self._user_ids:
            self._user_ids[namespace] = f"bench-{namespace}"
        user_id = self._user_ids[namespace]

        for turn in turns:
            msg = {
                "role": "user",
                "content": f"[{turn.speaker}] ({turn.session_id}): {turn.text}",
            }
            meta = {"dia_id": turn.dia_id, "session_id": turn.session_id}

            for attempt in range(self.max_retries + 1):
                try:
                    self._memory.add(
                        [msg],
                        user_id=user_id,
                        metadata=meta,
                        infer=self.infer,
                    )
                    break
                except Exception as e:
                    err = str(e)
                    if "429" in err:
                        wait = (2**attempt) * 5
                        print(f"    mem0 rate-limited, waiting {wait}s …")
                        time.sleep(wait)
                    elif attempt < self.max_retries:
                        time.sleep(1)
                    else:
                        print(f"    mem0 add error (fatal): {e}")
                        raise
            time.sleep(self.pacing)

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]:
        user_id = self._user_ids.get(namespace)
        if not user_id:
            return []

        results = self._memory.search(
            query=query,
            filters={"user_id": user_id},
            limit=k,
        )
        memories = (
            results.get("results", []) if isinstance(results, dict) else (results or [])
        )

        items: list[RetrievedItem] = []
        for mem in memories:
            text = mem.get("memory", "")

            # Prefer metadata over regex from text (metadata survives LLM extraction)
            meta = mem.get("metadata", {}) or {}
            dia_id = meta.get("dia_id", "")
            session_id = meta.get("session_id", "")

            # Fallback: try to match from text (for infer=False, raw text has tags)
            if not dia_id:
                m = re.search(r"\[dia_id=([^\]]+)\]", text)
                if m:
                    dia_id = m.group(1)
            if not session_id:
                m = re.search(r"\(([^)]+)\)", text)
                if m:
                    session_id = m.group(1)

            # Clean up the text
            clean = re.sub(r"\[dia_id=[^\]]*\]\s*", "", text)
            clean = re.sub(r"\[\w+\]\s*", "", clean)  # [speaker]

            items.append(
                RetrievedItem(
                    dia_id=dia_id,
                    session_id=session_id,
                    text=clean,
                    score=mem.get("score", 0.0),
                )
            )
        return items

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
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

            print(f"  [dry-run] store (infer={self.infer}) …")
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
