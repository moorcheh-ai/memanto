"""Memanto adapter — uses the repository's own SdkClient.

Requires ``MOORCHEH_API_KEY`` in the environment.
"""

from __future__ import annotations

import os
import time
import uuid

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class MemantoAdapter(MemorySystem):
    def __init__(
        self,
        api_key: str = "",
        pacing: float = 0.01,
        max_retries: int = 9,
    ):
        self.api_key = api_key
        self.pacing = pacing
        self.max_retries = max_retries
        self._client = None
        self._agent_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def name(self) -> str:
        return "memanto"

    # ------------------------------------------------------------------
    # setup / teardown
    # ------------------------------------------------------------------

    def setup(self) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        # Load all available keys for rotation
        self._keys: list[str] = []
        base_key = os.environ.get("MOORCHEH_API_KEY", "")
        if base_key:
            self._keys.append(base_key)
        for i in range(1, 20):
            k = os.environ.get(f"MOORCHEH_API_KEY_{i}", "")
            if k and k not in self._keys:
                self._keys.append(k)
        if not self._keys:
            raise ValueError("MOORCHEH_API_KEY not set")
        self._key_idx = 0
        self._client = SdkClient(api_key=self._keys[0])

    def teardown(self) -> None:
        self._agent_ids.clear()

    def cleanup(self) -> None:
        """Delete all bench-* agents, namespaces, and local sessions."""
        import os

        api_key = self.api_key or os.environ.get("MOORCHEH_API_KEY", "")

        # 1. Delete Moorcheh bench-* namespaces
        if api_key:
            try:
                from moorcheh_sdk import MoorchehClient

                mc = MoorchehClient(api_key=api_key)
                ns_list = mc.namespaces.list()
                for ns in ns_list.get("namespaces", []):
                    ns_name = ns.get("namespace_name", "")
                    if "bench-" in ns_name:
                        try:
                            mc.namespaces.delete(namespace_name=ns_name)
                            print(f"    memanto cleanup: deleted namespace {ns_name}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"    memanto namespace cleanup: {e}")

        # 2. Delete local sessions
        import shutil
        from pathlib import Path

        sessions = Path.home() / ".memanto" / "sessions"
        if sessions.exists():
            shutil.rmtree(sessions, ignore_errors=True)
            print(f"    memanto cleanup: removed {sessions}")

    # ------------------------------------------------------------------
    # store / search
    # ------------------------------------------------------------------

    def _retry(self, fn, *args, **kwargs):
        for attempt in range(self.max_retries + 1):
            try:
                r = fn(*args, **kwargs)
                time.sleep(self.pacing)
                return r
            except Exception as e:
                err = str(e)
                if "429" in err or "Limit Exceeded" in err or "Namespace limit" in err:
                    # Rotate to next key
                    self._key_idx = (self._key_idx + 1) % len(self._keys)
                    new_key = self._keys[self._key_idx]
                    from memanto.cli.client.sdk_client import SdkClient

                    self._client = SdkClient(api_key=new_key)
                    wait = (2**attempt) * 3
                    print(
                        f"    Memanto: switched to key {self._key_idx + 1}/{len(self._keys)}, waiting {wait}s …"
                    )
                    time.sleep(wait)
                elif attempt < self.max_retries:
                    time.sleep(1)
                else:
                    raise

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        if namespace in self._agent_ids:
            agent_id = self._agent_ids[namespace]
        else:
            agent_id = f"bench-{namespace}-{uuid.uuid4().hex[:6]}"
            try:
                self._retry(self._client.create_agent, agent_id)
                self._retry(self._client.activate_agent, agent_id)
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"    memanto: agent already exists, reusing {agent_id}")
                    try:
                        self._retry(self._client.activate_agent, agent_id)
                    except Exception:
                        pass
                else:
                    print(f"    memanto: cannot create agent ({e})")
                    return
            self._agent_ids[namespace] = agent_id

        for turn in turns:
            try:
                self._retry(
                    self._client.remember,
                    agent_id=agent_id,
                    memory_type="fact",
                    title=f"Turn {turn.dia_id}",
                    content=turn.text,
                    tags=[turn.session_id, turn.dia_id, turn.speaker],
                )
            except Exception as e:
                print(f"    Memanto remember error ({turn.dia_id}): {e}")

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]:
        agent_id = self._agent_ids.get(namespace)
        if not agent_id:
            return []

        # Ensure session is active before recall (memanto sessions expire)
        try:
            self._retry(self._client.activate_agent, agent_id)
        except Exception:
            pass

        try:
            result = self._retry(
                self._client.recall,
                agent_id,
                query,
                limit=k,
            )
        except Exception:
            return []

        items: list[RetrievedItem] = []
        if result is None:
            return items
        for mem in result.get("memories", [])[:k]:
            tags = mem.get("tags", []) or []
            dia_id = tags[1] if len(tags) > 1 else ""
            session_id = tags[0] if tags else ""
            items.append(
                RetrievedItem(
                    dia_id=dia_id,
                    session_id=session_id,
                    text=mem.get("content", mem.get("memory", "")),
                    score=mem.get("score", mem.get("similarity", 0.0)),
                )
            )
        return items

    # ------------------------------------------------------------------
    # dry-run
    # ------------------------------------------------------------------

    def dry_run(self) -> bool:
        from providers import check_keys

        if not check_keys("MOORCHEH_API_KEY"):
            return False
        print("    ✓  MOORCHEH_API_KEY")

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

            # Let store_turns handle agent creation + activation automatically
            print("  [dry-run] store …")
            self.store_turns([test_turn], ns)
            print("    ✓ store")

            # Extract the agent_id that store_turns created
            agent_id = self._agent_ids.get(ns, "")

            print("  [dry-run] search …")
            results = self.search("What color is the sky?", ns, k=3)
            found = any("cerulean" in r.text.lower() for r in results)
            print(
                f"    ✓ retrieved {len(results)} results, "
                f"contains-answer={'yes' if found else 'NO'}"
            )
            if not found and agent_id:
                # Debug: list all memories for this agent
                try:
                    all_mem = self._retry(self._client.recall, agent_id, "", limit=20)
                    print(
                        f"    debug: agent has {len(all_mem.get('memories', []))} memories"
                    )
                except Exception:
                    pass
                return False

            print("  [dry-run] teardown …")
            if agent_id:
                self._retry(self._client.delete_agent, agent_id)
            self.teardown()
            print("    ✓ teardown")
            return True
        except Exception as e:
            print(f"    ✗  dry-run failed: {e}")
            return False
