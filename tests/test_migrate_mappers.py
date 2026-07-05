from memanto.cli.migrate.mappers import map_mem0


def test_map_mem0_accepts_single_category_string():
    rows = map_mem0(
        {
            "memories": [
                {
                    "id": "mem-1",
                    "memory": "The user prefers concise PR summaries.",
                    "categories": "personal_preferences",
                }
            ]
        }
    )

    assert len(rows) == 1
    assert rows[0]["type"] == "preference"
    assert rows[0]["tags"] == ["personal_preferences"]
