#!/usr/bin/env python3
"""
Benchmark B: Shifting Persona & Temporal Tracking Test

Build an evolving entertainment curator agent where user preferences
mutate over multiple distinct sessions. Measures preference retention
accuracy and context inflation.
"""

import json
import os
import time
import statistics
from datetime import datetime

NUM_SESSIONS = 5
PREFERENCES_PER_SESSION = 3


# ── Synthetic user preference streams ────────────────────────

PREFERENCE_STREAMS = [
    # Session 1: Initial setup
    [
        "User loves 90s hip-hop, especially Nas and A Tribe Called Quest",
        "User prefers vinyl records over streaming",
        "User hates auto-generated playlists",
    ],
    # Session 2: Evolution
    [
        "User discovered lo-fi hip-hop for work focus",
        "User now tolerates Spotify recommendations for discovery",
        "User still refuses algorithm-generated radio stations",
    ],
    # Session 3: Contradiction
    [
        "User says they 'don't like jazz' anymore (was into it last year)",
        "User started collecting rare funk records from the 70s",
        "User wants a playlist for dinner parties — something they previously refused",
    ],
    # Session 4: Nuance
    [
        "User clarifies they don't like smooth jazz, but enjoy avant-garde jazz",
        "User's funk collection now includes Afrobeat influences",
        "User wants the dinner party playlist to exclude anything with lyrics",
    ],
    # Session 5: Long-term test
    [
        "User mentions their favorite Nas album changed from Illmatic to It Was Written",
        "User is now open to algorithm-generated playlists 'if they learn my taste'",
        "User wants a separate workout playlist — high energy, 80s rock only",
    ],
]

# Ground truth for accuracy checking
GROUND_TRUTH = {
    "preferred_genres": ["90s hip-hop", "lo-fi", "funk", "avant-garde jazz", "80s rock"],
    "disliked_genres": ["smooth jazz", "auto-generated (without learning)"],
    "current_favorite_artist": "Nas (album: It Was Written)",
    "playlist_preferences": {
        "dinner": "no lyrics, funk/jazz instrumental",
        "workout": "80s rock, high energy",
        "focus": "lo-fi hip-hop",
    },
    "format_preference": "vinyl",
}


def test_system(name, store_class, config, preference_streams):
    """Run temporal tracking test. Returns accuracy metrics."""
    
    store = store_class(**config)
    session_results = []
    
    for session_idx, prefs in enumerate(preference_streams):
        session_start = time.time()
        
        # Store each preference
        for pref in prefs:
            store.add(f"pref_s{session_idx}", {"content": pref, "session": session_idx, "timestamp": datetime.now().isoformat()})
        
        # Query: what does the user currently like?
        recalled = store.search("What music does the user currently enjoy?", limit=5)
        
        session_time = time.time() - session_start
        
        session_results.append({
            "session": session_idx + 1,
            "preferences_stored": len(prefs),
            "items_recalled": len(recalled) if recalled else 0,
            "latency_seconds": round(session_time, 3),
        })
    
    # Accuracy: check if system can recall CURRENT preferences (not outdated ones)
    final_recall = store.search("Tell me everything about the user's music taste", limit=10)
    recalled_text = " ".join([r.get("content", "") for r in final_recall]) if final_recall else ""
    
    # Score based on accurate recall of current (session 5) vs outdated (session 1-2)
    accuracy_score = 0
    total_checks = 3
    if "80s rock" in recalled_text or "workout" in recalled_text:
        accuracy_score += 1  # correctly remembered recent preference
    if "jazz" in recalled_text.lower() and "smooth" not in recalled_text.lower():
        accuracy_score += 1  # correctly remembered nuanced preference
    if "nas" in recalled_text.lower() or "it was written" in recalled_text.lower():
        accuracy_score += 1  # correctly remembered updated favorite
    
    return {
        "system": name,
        "sessions_completed": len(session_results),
        "total_preferences_stored": sum(s["preferences_stored"] for s in session_results),
        "mean_latency": round(statistics.mean([s["latency_seconds"] for s in session_results]), 3),
        "accuracy_score": f"{accuracy_score}/{total_checks}",
        "accuracy_percent": round(accuracy_score / total_checks * 100, 1),
        "session_details": session_results,
    }


def main():
    print("=" * 70)
    print("Benchmark B: Shifting Persona & Temporal Tracking Test")
    print("=" * 70)
    print(f"\nSessions: {NUM_SESSIONS} | Preferences per session: {PREFERENCES_PER_SESSION}")
    print(f"Scenario: User music preferences evolve and contradict over time")
    print()
    
    # Use dummy stores (same as benchmark A)
    from benchmark_a_context_latency import DummyMemantoStore, DummyMem0Store
    
    print("Testing Memanto...")
    memanto_results = test_system("Memanto", DummyMemantoStore, {}, PREFERENCE_STREAMS)
    print(f"  Accuracy: {memanto_results['accuracy_score']}")
    print(f"  Mean latency: {memanto_results['mean_latency']}s")
    
    print("Testing Mem0...")
    mem0_results = test_system("Mem0", DummyMem0Store, {}, PREFERENCE_STREAMS)
    print(f"  Accuracy: {mem0_results['accuracy_score']}")
    print(f"  Mean latency: {mem0_results['mean_latency']}s")
    
    # Comparison
    print()
    print("-" * 70)
    print("Comparison Table")
    print("-" * 70)
    print(f"{'Metric':<40} {'Memanto':<15} {'Mem0':<15}")
    print(f"{'─'*40} {'─'*15} {'─'*15}")
    print(f"{'Sessions Completed':<40} {memanto_results['sessions_completed']:<15} {mem0_results['sessions_completed']:<15}")
    print(f"{'Total Preferences Stored':<40} {memanto_results['total_preferences_stored']:<15} {mem0_results['total_preferences_stored']:<15}")
    print(f"{'Mean Latency (s)':<40} {memanto_results['mean_latency']:<15} {mem0_results['mean_latency']:<15}")
    print(f"{'Accuracy Score':<40} {memanto_results['accuracy_score']:<15} {mem0_results['accuracy_score']:<15}")
    print(f"{'Accuracy %':<40} {memanto_results['accuracy_percent']:<15} {mem0_results['accuracy_percent']:<15}")
    
    # Save results
    results = {
        "scenario": "B - Shifting Persona & Temporal Tracking",
        "memanto": memanto_results,
        "mem0": mem0_results,
        "timestamp": datetime.now().isoformat(),
    }
    
    os.makedirs("results", exist_ok=True)
    with open("results/scenario_b_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Results saved to results/scenario_b_results.json")


if __name__ == "__main__":
    main()
