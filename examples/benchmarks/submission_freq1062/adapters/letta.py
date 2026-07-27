"""Letta (MemGPT) adapter — uses ``letta_client`` SDK.

Letta is a platform for stateful agents with advanced memory.

Setup:
    pip install letta letta-client asyncpg
    letta server  # starts on localhost:8283

API (letta_client v1.12+):
    client.agents.create() / delete()
    client.archives.create(agent_id, content)
    client.passages.search(query, agent_id)
"""

from __future__ import annotations

import re
import uuid

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class LettaAdapter(MemorySystem):
    _required_env: list[str] = []

    def __init__(self, base_url: str = "http://localhost:8283"):
        self.base_url = base_url
        self._client = None
        self._agent_ids: dict[str, str] = {}

    def name(self) -> str:
        return "letta"

    def setup(self) -> None:
        # Ensure SQLite DB is initialized (safe to call even if tables exist)
        self._maybe_init_db()

        from letta_client import Letta

        self._client = Letta(
            base_url=self.base_url,
            environment="local",
            api_key="",
        )

    @staticmethod
    def _maybe_init_db() -> None:
        """Create Letta SQLite tables if they don't exist.

        Letta v0.16.x does not auto-create SQLite tables on startup.
        This is a workaround that calls ``Base.metadata.create_all()``
        on the SQLite database before the server starts.
        """
        import asyncio
        import os

        db_path = os.path.expanduser("~/.letta/letta.db")
        if os.path.exists(db_path):
            return  # db already initialized

        try:
            os.environ.setdefault("LETTA_DB_DIR", os.path.expanduser("~/.letta"))

            # Import the ORM base and engine (same as the server)
            from letta.settings import settings

            # Force settings evaluation to pick up LETTA_DB_DIR
            _ = settings.database_engine

            from letta.orm import Base
            from letta.server.db import engine as _async_engine

            async def _create():
                async with _async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

            asyncio.run(_create())
            print("    letta: SQLite tables created")
        except Exception:
            # Tables might have been created by a previous run, or
            # the user is using PostgreSQL — continue anyway.
            pass

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        if namespace not in self._agent_ids:
            agent_id = f"bench-{namespace}-{uuid.uuid4().hex[:8]}"
            self._client.agents.create(
                name=agent_id,
                memory_blocks=[
                    {
                        "label": "human",
                        "value": f"Benchmark user {namespace}",
                        "limit": 2000,
                    }
                ],
            )
            self._agent_ids[namespace] = agent_id

        agent_id = self._agent_ids[namespace]
        for turn in turns:
            try:
                self._client.archives.create(
                    agent_id=agent_id,
                    content=f"[dia_id={turn.dia_id}] [{turn.speaker}] {turn.text}",
                )
            except Exception as e:
                print(f"    Letta archive error: {e}")

    def search(self, query: str, namespace: str, k: int = 10) -> list[RetrievedItem]:
        agent_id = self._agent_ids.get(namespace)
        if not agent_id:
            return []

        try:
            results = self._client.passages.search(
                query=query,
                agent_id=agent_id,
            )
        except Exception as e:
            print(f"    Letta search error: {e}")
            return []

        items = []
        for p in (results or [])[:k]:
            text = getattr(p, "content", str(p))
            dia_match = re.search(r"\[dia_id=([^\]]+)\]", text)
            dia_id = dia_match.group(1) if dia_match else ""
            clean = re.sub(r"\[dia_id=[^\]]*\]\s*", "", text)
            items.append(
                RetrievedItem(
                    dia_id=dia_id,
                    session_id="",
                    text=clean,
                    score=getattr(p, "score", 0.0),
                )
            )
        return items

    def teardown(self) -> None:
        for agent_id in self._agent_ids.values():
            try:
                self._client.agents.delete(id=agent_id)
            except Exception:
                pass
        self._agent_ids.clear()

    def cleanup(self) -> None:
        import shutil
        from pathlib import Path

        for p in [Path.home() / ".letta"]:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                print(f"    letta cleanup: removed {p}")
            else:
                print(f"    letta cleanup: {p} not found")

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
        print(f"  [dry-run] checking {self.base_url} …")
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
