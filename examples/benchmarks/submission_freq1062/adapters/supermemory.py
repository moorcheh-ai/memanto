"""Supermemory adapter — memory and context engine for AI.

Uses the ``supermemory`` Python SDK (``pip install supermemory``).

Infrastructure:
- Cloud: ``SUPERMEMORY_API_KEY`` env var
- Local: ``npx supermemory local`` (Node.js, port 6767)

API docs: https://supermemory.ai/docs/search, https://supermemory.ai/docs/add-memories
"""

from __future__ import annotations

import re
import time
import uuid

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class SupermemoryAdapter(MemorySystem):
    _required_env: list[str] = ["SUPERMEMORY_API_KEY"]

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self._client = None
        self._container_tags: dict[str, str] = {}

    def name(self) -> str:
        return "supermemory"

    def setup(self) -> None:
        import os

        from supermemory import Supermemory

        api_key = self.api_key or os.environ.get("SUPERMEMORY_API_KEY", "")
        if not api_key:
            raise ValueError("SUPERMEMORY_API_KEY required in .env")
        self._client = Supermemory(api_key=api_key)

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        tag = self._container_tags.get(namespace)
        if not tag:
            tag = f"bench-{namespace}-{uuid.uuid4().hex[:8]}"
            self._container_tags[namespace] = tag

        for turn in turns:
            content = (
                f"[dia_id={turn.dia_id}] [session={turn.session_id}] "
                f"{turn.speaker}: {turn.text}"
            )
            try:
                self._client.add(
                    content=content,
                    container_tag=tag,
                    dreaming="instant",
                )
            except Exception as e:
                print(f"    Supermemory add error: {e}")

            time.sleep(0.05)

    def search(self, query: str, namespace: str, k: int = 10) -> list[RetrievedItem]:
        tag = self._container_tags.get(namespace)
        if not tag:
            return []

        # Poll up to 3 times for async indexing
        for _attempt in range(3):
            try:
                resp = self._client.search.documents(
                    q=query,
                    container_tags=[tag],
                    limit=k,
                )
                raw = list(resp.results or []) if hasattr(resp, "results") else []
            except Exception as e:
                print(f"    Supermemory search error: {e}")
                return []

            items = []
            for mem in raw[:k]:
                # Extract text from chunks (ResultChunk objects have .content)
                chunks = getattr(mem, "chunks", None) or []
                if isinstance(chunks, list) and chunks:
                    if hasattr(chunks[0], "content"):
                        text = " ".join(c.content for c in chunks)
                    elif hasattr(chunks[0], "text"):
                        text = " ".join(c.text for c in chunks)
                    else:
                        text = " ".join(str(c) for c in chunks)
                else:
                    text = getattr(mem, "memory", "") or str(mem)

                dia_match = re.search(r"\[dia_id=([^\]]+)\]", text)
                ses_match = re.search(r"\[session=([^\]]+)\]", text)
                dia_id = dia_match.group(1) if dia_match else ""
                session = ses_match.group(1) if ses_match else ""
                clean = re.sub(r"\[(dia_id|session)=[^\]]*\]\s*", "", text)
                items.append(
                    RetrievedItem(
                        dia_id=dia_id,
                        session_id=session,
                        text=clean,
                        score=getattr(mem, "similarity", 0.0) or 0.0,
                    )
                )

            if items:
                return items
            time.sleep(2)  # Wait for async indexing

        return items

    def teardown(self) -> None:
        self._container_tags.clear()

    def cleanup(self) -> None:
        """Delete all documents from Supermemory."""
        import os

        try:
            from supermemory import Supermemory

            api_key = os.environ.get("SUPERMEMORY_API_KEY", "")
            if not api_key:
                print("    supermemory cleanup: SUPERMEMORY_API_KEY not set")
                return
            cli = Supermemory(api_key=api_key)
            total = 0
            while True:
                resp = cli.documents.list()
                mems = (
                    resp.memories
                    if hasattr(resp, "memories")
                    else (resp.results if hasattr(resp, "results") else [])
                )
                if not mems:
                    break
                ids = [m.id for m in mems if hasattr(m, "id")]
                if ids:
                    cli.documents.delete_bulk(ids=ids)
                    total += len(ids)
                else:
                    break
            if total:
                print(f"    supermemory cleanup: deleted {total} documents")
        except Exception as e:
            print(f"    supermemory cleanup: {e}")
