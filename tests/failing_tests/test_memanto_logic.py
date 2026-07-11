from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel

# Standardized imports from Memanto core
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService

# Mock MoorchehClient to test local logic flow
class DummyDocuments:
    def __init__(self):
        self.stored_docs = {}

    def upload(self, namespace_name: str, documents: list[dict[str, Any]]):
        if namespace_name not in self.stored_docs:
            self.stored_docs[namespace_name] = []
        self.stored_docs[namespace_name].extend(documents)
        return {"status": "success", "uploaded": len(documents)}

class DummyMoorchehClient:
    def __init__(self):
        self.documents = DummyDocuments()

def test_chronology_overwrite():
    client = DummyMoorchehClient()
    writer = MemoryWriteService(client)

    # 1. Simulate an event occurring 5 days ago
    historical_time = datetime.utcnow() - timedelta(days=5)
    record = MemoryRecord(
        title="Database migration",
        content="Migrated development db to PostgreSQL",
        agent_id="test_agent",
        actor_id="user_1",
        source="system",
        provenance="explicit_statement", # Default value
        created_at=historical_time
    )

    print(f"[Pre-Ingestion] Record intended created_at: {record.created_at}")

    # 2. Store the record using the service
    result = writer.store_memory(record)

    # 3. Retrieve the processed document dictionary format
    doc = record.to_moorcheh_document()
    processed_created_at = datetime.fromisoformat(doc["created_at"])

    print(f"[Post-Ingestion] Record actual created_at: {processed_created_at}")
    
    # Assert whether the timeline timestamp was preserved
    time_difference = abs((processed_created_at - historical_time).total_seconds())
    assert time_difference <= 10

def test_contradiction_handling():
    client = DummyMoorchehClient()
    writer = MemoryWriteService(client)

    # Ingest two directly contradictory facts
    fact_1 = MemoryRecord(
        title="Programming language choice",
        content="I prefer writing application logic in Python.",
        agent_id="test_agent",
        actor_id="user_1",
        source="user"
    )
    fact_2 = MemoryRecord(
        title="Programming language choice update",
        content="I prefer writing application logic in Go.",
        agent_id="test_agent",
        actor_id="user_1",
        source="user"
    )

    print("\nIngesting contradictory statements:")
    res_1 = writer.store_memory(fact_1)
    res_2 = writer.store_memory(fact_2)

    print(f"Statement 1 Status: {res_1['status']} (Action: {res_1['action']})")
    print(f"Statement 2 Status: {res_2['status']} (Action: {res_2['action']})")
    print("-> Note: Both conflicting facts co-exist in storage with no deduplication or resolution.")

    # Inspect the updated mock storage dictionary and assert coexistence
    stored_docs = client.documents.stored_docs.get("memanto_agent_test_agent", [])
    assert len(stored_docs) == 2

if __name__ == "__main__":
    print("=== Testing Timeline Chronology ===")
    test_chronology_overwrite()
    print("\n=== Testing Contradiction Handling ===")
    test_contradiction_handling()
