from build_report import build_report


def test_report_separates_physical_bytes_from_token_estimate():
    text = build_report(
        {
            "source_tool": "Hermes Holographic MemoryStore",
            "entity_count": 9,
            "fact_entity_association_count": 12,
            "sqlite_integrity_check": "ok",
            "source_search_latency_ms": [1.0, 2.0, 3.0],
            "source_search_latency_median_ms": 2.0,
        },
        {
            "source_facts": 72,
            "exported_memories": 72,
            "per_type": {"fact": 60, "preference": 12},
            "source_sqlite_bytes": 1000,
            "okf_bundle_bytes": 800,
            "bundle_file_count": 76,
            "approx_canonical_content_tokens": 123,
            "source_accounting": {
                "canonical_content_bytes": 492,
                "canonical_tag_bytes": 40,
                "hrr_vector_bytes": 2048,
                "memory_bank_vector_bytes": 1024,
            },
            "derived_not_serialized": {
                "facts_fts_present": True,
                "hrr_vector_fact_count": 72,
                "memory_bank_count": 2,
            },
            "source_sha256": "a" * 64,
            "bundle_manifest_sha256": "b" * 64,
        },
        {
            "status": "PASS",
            "checked_fields": 1008,
            "mismatches": [],
            "okf_memories": 72,
        },
    )
    assert "Source facts: **72**" in text
    assert "Field assertions checked: **1008**" in text
    assert "not** described as token savings" in text
    assert "Approx. canonical-content tokens" in text
