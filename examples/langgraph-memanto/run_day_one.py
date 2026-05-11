"""Day-one script: store support memories in Memanto."""

from __future__ import annotations

from run_full_demo import create_memory
from support_graph import seed_yesterday


if __name__ == "__main__":
    memory = create_memory()
    seed_yesterday(memory)
    print("Stored day-one support memories for user 'maya'.")
