"""Run Agno's real SQLite persistence API with a documented demonstration scenario."""

import argparse
from pathlib import Path

from agno.db.schemas.memory import UserMemory
from agno.db.sqlite import SqliteDb


def populate(path: Path) -> None:
    if path.exists():
        raise FileExistsError("The demo only creates new databases")
    path.parent.mkdir(parents=True, exist_ok=True)
    database = SqliteDb(db_file=str(path))
    memories = [
        ("delivery", "Deliver the weekly report on Monday at 09:00 UTC.", ["schedule"]),
        ("format", "Send reports as Markdown, with a CSV attachment.", ["format"]),
        (
            "locale",
            "The project displays times in Asia/Kolkata and uses INR.",
            ["locale"],
        ),
        (
            "storage",
            "The project stores its primary data in PostgreSQL 16.",
            ["database"],
        ),
    ]
    for memory_id, content, topics in memories:
        saved = database.upsert_user_memory(
            UserMemory(
                memory_id=memory_id,
                memory=content,
                topics=topics,
                user_id="demo-user",
                agent_id="report-assistant",
            )
        )
        assert saved is not None
    # A correction replaces the old source record before export.
    saved = database.upsert_user_memory(
        UserMemory(
            memory_id="delivery",
            memory="Correction: deliver the weekly report on Friday at 16:00 UTC.",
            topics=["schedule"],
            user_id="demo-user",
            agent_id="report-assistant",
            input="Move Monday delivery to Friday afternoon.",
        )
    )
    assert saved is not None
    saved = database.upsert_user_memory(
        UserMemory(
            memory_id="other-user",
            memory="A separate user's memory must stay separate.",
            user_id="other-user",
        )
    )
    assert saved is not None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    populate(parser.parse_args().database)
