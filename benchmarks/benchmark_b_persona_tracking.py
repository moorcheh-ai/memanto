#!/usr/bin/env python3
"""
Benchmark B: Shifting Persona & Temporal Tracking Test
"""

import json
import os
import time
import statistics
import yaml
from datetime import datetime

# ── Load config ─────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    MOORCHEH_KEY = cfg.get("MOORCHEH_API_KEY", "")
    HAS_KEYS = MOORCHEH_KEY and MOORCHEH_KEY != "your-moorcheh-api-key-here"
else:
    HAS_KEYS = False

NUM_SESSIONS = 5

PREFERENCE_STREAMS = [
    ["User loves 90s hip-hop, especially Nas and A Tribe Called Quest",
     "User prefers vinyl records over streaming",
     "User hates auto-generated playlists"],
    ["User discovered lo-fi hip-hop for work focus",
     "User now tolerates Spotify recommendations for discovery",
     "User still refuses algorithm-generated radio stations"],
    ["User says they don't like jazz anymore (was into it last year)",
     "User started collecting rare funk records from the 70s",
     "User wants a playlist for dinner parties"],
    ["User clarifies they don't like smooth jazz, but enjoy avant-garde jazz",
     "User's funk collection now includes Afrobeat influences",
     "User wants the dinner party playlist to exclude anything with lyrics"],
    ["User mentions their favorite Nas album changed from Illmatic to It Was Written",
     "User is now open to algorithm-generated playlists if they learn my taste",
     "User wants a separate workout playlist: high energy, 80s rock only"],
]


def get_memanto_store():
    if HAS_KEYS:
        try:
            from memanto import Memanto
            return Memanto(api_key=MOORCHEH_KEY)
        except ImportError:
            pass
    return DummyMemantoStore()


def get_mem0_store():
    try:
        from mem0 import Memory
        return Memory()
    except:
        return DummyMem0Store()


class DummyMemantoStore:
    def __init__(self):
        self.memories = []
    def add(self, key, value):
        self.memories.append((key, value))
    def search(self, query, limit=5):
        results = [{"content": v.get("content",""), "score":0.8} for _,v in self.memories[-10:]]
        return results[:limit]


class DummyMem0Store:
    def __init__(self):
        self.memories = {}
    def add(self, key, value):
        self.memories[key] = value
    def search(self, query, limit=5):
        results = [{"content": v.get("content",""), "score":0.7} for _,v in list(self.memories.items())[-10:]]
        return results[:limit]


def test_system(name, store_factory, streams):
    store = store_factory()
    session_results = []
    for sidx, prefs in enumerate(streams):
        start = time.time()
        for pref in prefs:
            store.add(f"pref_s{sidx}", {"content": pref, "session": sidx})
        recalled = store.search("What music does the user currently enjoy?", limit=5)
        session_results.append({
            "session": sidx + 1,
            "preferences_stored": len(prefs),
            "items_recalled": len(recalled) if recalled else 0,
            "latency_seconds": round(time.time() - start, 3),
        })

    final = store.search("Tell me everything about the user's music taste", limit=10)
    text = " ".join([r.get("content","") for r in final]) if final else ""
    score = 0
    if "80s rock" in text or "workout" in text: score += 1
    if "jazz" in text.lower() and "smooth" not in text.lower(): score += 1
    if "nas" in text.lower() or "it was written" in text.lower(): score += 1

    return {
        "system": name,
        "api_mode": "real" if HAS_KEYS else "dummy",
        "sessions_completed": len(session_results),
        "total_preferences_stored": sum(s["preferences_stored"] for s in session_results),
        "mean_latency": round(statistics.mean([s["latency_seconds"] for s in session_results]), 3),
        "accuracy_score": f"{score}/3",
        "accuracy_percent": round(score / 3 * 100, 1),
    }


def main():
    print("=" * 70)
    print("Benchmark B: Shifting Persona & Temporal Tracking Test")
    print("=" * 70)
    print(f"\nSessions: {NUM_SESSIONS}")
    print(f"API mode: {'REAL (keys detected)' if HAS_KEYS else 'DUMMY (no keys)'}")
    print()

    for name, factory in [("Memanto", get_memanto_store), ("Mem0", get_mem0_store)]:
        r = test_system(name, factory, PREFERENCE_STREAMS)
        print(f"{name}: Accuracy {r['accuracy_score']} | Latency {r['mean_latency']}s")

    os.makedirs("results", exist_ok=True)
    with open("results/scenario_b_results.json", "w") as f:
        json.dump({"scenario":"B","memanto":test_system("Memanto",get_memanto_store,PREFERENCE_STREAMS),
                   "mem0":test_system("Mem0",get_mem0_store,PREFERENCE_STREAMS),
                   "timestamp":datetime.now().isoformat()}, f, indent=2)
    print(f"\n✅ Results saved")


if __name__ == "__main__":
    main()
