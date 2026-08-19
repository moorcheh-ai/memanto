"""Zep Cloud memory system adapter (zep-cloud >= 3.0).

Uses batch ingestion for reliable processing (individual ``graph.add()``
calls never finish indexing on the free tier; batch forces it).
"""

from __future__ import annotations

import json
import os
import time
import uuid

from interfaces import DialogueTurn, MemorySystem, RetrievedItem


class ZepAdapter(MemorySystem):
    def __init__(self, api_key: str = "", batch_timeout: int = 120):
        self.api_key = api_key
        self.batch_timeout = batch_timeout
        self._client = None
        self._user_ids: dict[str, str] = {}
        self._graph_ids: dict[str, str] = {}
        self._batch_ids: dict[str, list[str]] = {}

    def name(self) -> str:
        return "zep"

    def setup(self) -> None:
        from zep_cloud import Zep

        api_key = self.api_key or os.environ.get("ZEP_API_KEY", "")
        if not api_key:
            raise ValueError("ZEP_API_KEY required")
        self._client = Zep(api_key=api_key)

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None:
        from zep_cloud.types import BatchAddItem

        if namespace not in self._user_ids:
            uid = f"bench-{namespace}-{uuid.uuid4().hex[:8]}"
            gid = f"graph-{uid}"
            self._client.user.add(user_id=uid)
            self._client.graph.create(graph_id=gid)
            self._user_ids[namespace] = uid
            self._graph_ids[namespace] = gid

        uid = self._user_ids[namespace]
        gid = self._graph_ids[namespace]

        # Build batch items
        items = [
            BatchAddItem(
                user_id=uid,
                type="graph_episode",
                data_type="message",
                data=json.dumps(
                    {
                        "role": turn.speaker,
                        "content": f"[dia_id={turn.dia_id}] {turn.text}",
                    }
                ),
            )
            for turn in turns
        ]

        # Zep batches max at 350 items — split if needed
        chunk_size = 300
        for chunk_start in range(0, len(items), chunk_size):
            chunk = items[chunk_start : chunk_start + chunk_size]
            self._submit_zep_batch(chunk, uid, namespace)

        # Poll for completion (only need to poll the last batch)
        self._poll_zep_batches(namespace)

    def _submit_zep_batch(self, items: list, uid: str, namespace: str) -> None:
        """Submit a single batch of items to Zep."""
        import re

        try:
            batch = self._client.batch.create()
            bid = batch.batch_id
            self._client.batch.add(bid, items=items)
            self._client.batch.process(bid)
            self._batch_ids.setdefault(namespace, []).append(bid)
            print(f"    zep: batch {bid[:12]}... submitted ({len(items)} items)")
        except Exception as e:
            err = str(e)
            if "429" in err or "retry-after" in err.lower():
                wait_m = re.search(r"retry-after:\s*(\d+)", err, re.IGNORECASE)
                w = int(wait_m.group(1)) + 5 if wait_m else 60
                print(f"    zep rate-limited, waiting {w}s …")
                time.sleep(w)
                # Retry once
                batch = self._client.batch.create()
                bid = batch.batch_id
                self._client.batch.add(bid, items=items)
                self._client.batch.process(bid)
                self._batch_ids.setdefault(namespace, []).append(bid)
                print(f"    zep: batch {bid[:12]}... submitted on retry")
            else:
                print(f"    zep batch error: {e}")
                # Fallback: individual adds with rate handling
                for item in items:
                    for _attempt in range(3):
                        try:
                            self._client.graph.add(**item)
                            break
                        except Exception as e2:
                            if "429" in str(e2) or "retry-after" in str(e2).lower():
                                wm = re.search(
                                    r"retry-after:\s*(\d+)", str(e2), re.IGNORECASE
                                )
                                w = int(wm.group(1)) + 2 if wm else 30
                                time.sleep(w)
                            else:
                                break

    def _poll_zep_batches(self, namespace: str) -> None:
        """Poll all submitted batches for completion."""
        bids = self._batch_ids.get(namespace, [])
        if not bids:
            return
        deadline = time.time() + self.batch_timeout
        remaining = list(bids)
        while remaining and time.time() < deadline:
            for bid in list(remaining):
                try:
                    status = self._client.batch.get(bid)
                    s = getattr(status, "status", "")
                    prog = getattr(status, "progress", None)
                    if prog:
                        p = f"{getattr(prog, 'succeeded_items', 0)}/{getattr(prog, 'total_items', 0)}"
                    else:
                        p = "?"
                    print(f"    zep batch {bid[:12]}: {s} ({p})")
                    if s == "succeeded":
                        remaining.remove(bid)
                    elif s == "failed":
                        print(f"    zep batch {bid[:12]}: FAILED")
                        remaining.remove(bid)
                except Exception:
                    pass
            if remaining:
                time.sleep(5)
                if s in ("succeeded", "failed"):
                    break
                time.sleep(5)

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]:
        import re

        uid = self._user_ids.get(namespace)
        if not uid:
            return []

        try:
            result = self._client.graph.search(
                user_id=uid,
                query=query,
                scope="episodes",
                limit=k,
            )
        except Exception as e:
            print(f"    zep search error: {e}")
            return []

        items: list[RetrievedItem] = []
        seen: set[str] = set()
        for ep in (getattr(result, "episodes", None) or [])[:k]:
            text = ep.content or ""
            dia = re.search(r"\[dia_id=([^\]]+)\]", text)
            dia_id = dia.group(1) if dia else ep.uuid_ or ""
            if dia_id in seen:
                continue
            seen.add(dia_id)
            clean = re.sub(r"\[dia_id=[^\]]*\]\s*", "", text)
            items.append(
                RetrievedItem(
                    dia_id=dia_id,
                    session_id=uid,
                    text=clean,
                    score=ep.score or 0.0,
                )
            )
        return items[:k]

    def teardown(self) -> None:
        for gid in self._graph_ids.values():
            try:
                self._client.graph.delete(graph_id=gid)
            except Exception:
                pass
        for uid in self._user_ids.values():
            try:
                self._client.user.delete(uid)
            except Exception:
                pass
        self._user_ids.clear()
        self._graph_ids.clear()
        self._batch_ids.clear()

    def cleanup(self) -> None:
        try:
            from zep_cloud import Zep

            key = os.environ.get("ZEP_API_KEY", "")
            if not key:
                return
            cli = Zep(api_key=key)
            for g in cli.graph.list_all() or []:
                gid = g.graph_id if hasattr(g, "graph_id") else str(g)
                if "bench-" in gid:
                    try:
                        cli.graph.delete(graph_id=gid)
                    except Exception:
                        pass
            for u in cli.user.list_ordered() or []:
                uid = u.user_id if hasattr(u, "user_id") else str(u)
                if "bench-" in uid:
                    try:
                        cli.user.delete(uid)
                    except Exception:
                        pass
        except Exception:
            pass

    def dry_run(self) -> bool:
        from providers import check_keys

        if not check_keys("ZEP_API_KEY"):
            return False
        ns = f"dry-{uuid.uuid4().hex[:6]}"
        t = DialogueTurn(
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
            self.store_turns([t], ns)
            print("    ✓ store")
            print("  [dry-run] search …")
            r = self.search("What color is the sky?", ns, k=3)
            print(f"    ✓ {len(r)} results")
            return any("cerulean" in x.text.lower() for x in r)
        except Exception as e:
            print(f"    ✗  {e}")
            return False
        finally:
            try:
                self.teardown()
            except Exception:
                pass
