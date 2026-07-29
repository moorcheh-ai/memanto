"""Cognee adapter — local LLM + local embeddings via HTTP API server.

Defaults:
    LLM:      openai / local-model  (via http://127.0.0.1:8080/v1)
    Embedder: openai / local-model  (via http://127.0.0.1:8080/v1, 384d)

Requires the local API server running: ``python3 local_server.py &``
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class CogneeAdapter(MemorySystem):
    def __init__(
        self,
        llm_provider: str = "openai",
        llm_model: str = "local-model",
        embedder_provider: str = "openai",
        embedder_model: str = "all-MiniLM-L6-v2",
        embedder_endpoint: str = "http://127.0.0.1:8080/v1",
        embedder_dims: int = 384,
        pacing: float = 0.0,
        max_retries: int = 5,
    ):
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.embedder_provider = embedder_provider
        self.embedder_model = embedder_model
        self.embedder_endpoint = embedder_endpoint
        self.embedder_dims = embedder_dims
        self.pacing = pacing
        self.max_retries = max_retries
        self._session_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def name(self) -> str:
        return "cognee"

    # ------------------------------------------------------------------
    # Async helpers
    # ------------------------------------------------------------------

    def _run_async(self, coro):
        """Run a coroutine synchronously — handles both fresh and running loops."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import threading

            result: list = []
            error: list = []

            def _target() -> None:
                try:
                    nl = asyncio.new_event_loop()
                    result.append(nl.run_until_complete(coro))
                except Exception as e:
                    error.append(e)
                finally:
                    nl.close()

            t = threading.Thread(target=_target)
            t.start()
            t.join()
            if error:
                raise error[0]
            return result[0]
        return loop.run_until_complete(coro)

    # ------------------------------------------------------------------
    # setup / teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        import cognee

        # Use local API server for both LLM and embeddings
        local_url = self.embedder_endpoint
        local_key = "local-key"

        cognee.config.set_llm_api_key(local_key)
        cognee.config.set_llm_provider(self.llm_provider)
        cognee.config.set_llm_model(self.llm_model)
        cognee.config.set_llm_endpoint(local_url)

        # Embeddings via cluster (OpenAI-compatible, no rate limits)
        cognee.config.set_embedding_provider(self.embedder_provider)
        cognee.config.set_embedding_model(self.embedder_model)
        cognee.config.set_embedding_endpoint(local_url)
        cognee.config.set_embedding_api_key(local_key)
        cognee.config.set_embedding_dimensions(self.embedder_dims)

        os.environ.setdefault("POSTHOG_DISABLED", "true")

    def teardown(self) -> None:
        try:
            import cognee

            self._run_async(cognee.forget())
        except Exception:
            pass
        self._session_ids.clear()

    def cleanup(self) -> None:
        import shutil
        from pathlib import Path

        for p in [Path.home() / ".cognee"]:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                print(f"    cognee cleanme: removed {p}")

    # ------------------------------------------------------------------
    # store / search
    # ------------------------------------------------------------------

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        import cognee

        sid = self._session_ids.get(namespace)
        if not sid:
            sid = f"bench-{namespace}"
            self._session_ids[namespace] = sid

        texts = [
            f"[dia_id={t.dia_id}] [session={t.session_id}] {t.speaker}: {t.text}"
            for t in turns
        ]
        # Batch to avoid overwhelming the graph builder
        for i in range(0, len(texts), 3):
            batch = texts[i : i + 3]
            for attempt in range(self.max_retries + 1):
                try:
                    self._run_async(
                        cognee.remember(
                            data=batch,
                            dataset_name=namespace,
                            session_id=sid,
                        )
                    )
                    break
                except Exception as e:
                    err = str(e)
                    if "429" in err:
                        time.sleep((2**attempt) * 3)
                    elif attempt < self.max_retries:
                        time.sleep(1)
                    else:
                        print(f"    cognee remember error: {e}")
                        raise
            time.sleep(self.pacing)

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]:
        import cognee

        sid = self._session_ids.get(namespace)

        try:
            results = self._run_async(
                cognee.recall(
                    query_text=query,
                    top_k=k,
                    session_id=sid,
                    only_context=True,
                )
            )
        except Exception as e:
            if "Could not automatically map" in str(e):
                # Cognee needs tiktoken; force it
                import tiktoken

                tiktoken.get_encoding("cl100k_base")
                results = self._run_async(
                    cognee.recall(
                        query_text=query,
                        top_k=k,
                        session_id=sid,
                        only_context=True,
                    )
                )
            else:
                print(f"    cognee recall error: {e}")
                return []

        items: list[RetrievedItem] = []
        for r in (results or [])[:k]:
            text = getattr(r, "text", getattr(r, "content", str(r)))
            dia = re.search(r"\[dia_id=([^\]]+)\]", text)
            ses = re.search(r"\[session=([^\]]+)\]", text)
            clean = re.sub(r"\[(dia_id|session)=[^\]]*\]\s*", "", text)
            items.append(
                RetrievedItem(
                    dia_id=dia.group(1) if dia else "",
                    session_id=ses.group(1) if ses else "",
                    text=clean,
                    score=getattr(r, "score", 0.0),
                )
            )
        return items

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
        """Verify the adapter works with the local API server."""
        # Check local server is reachable
        import urllib.request

        try:
            urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
        except Exception:
            print("    ✗  Local API server not running on http://127.0.0.1:8080")
            print("       Start it: python3 local_server.py &")
            return False

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
