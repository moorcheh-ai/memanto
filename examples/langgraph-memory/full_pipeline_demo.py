import asyncio
import os
from integrations.langgraph.memanto_langgraph import MemantoStore, MemantoStoreConfig

async def verify_persistence():
    config = MemantoStoreConfig(
        api_key=os.getenv("MEMANTO_API_KEY", "dev_key"),
        default_namespace="persistence_test"
    )

    # Session A: Write typed memory
    store_a = MemantoStore(config)
    user_profile = {"user_id": 123, "preferences": {"theme": "dark", "lang": "en"}}
    
    print("Session A: Writing memory...")
    await store_a.put("user_profiles", "user_123", user_profile)

    # Session B: Retrieve memory using a fresh store instance
    store_b = MemantoStore(config)
    print("Session B: Retrieving memory...")
    retrieved_profile = await store_b.get("user_profiles", "user_123")

    print(f"Retrieved: {retrieved_profile}")
    assert retrieved_profile == user_profile, "Cross-session persistence failed"
    print("Verification successful: Memory persisted across store instances.")

if __name__ == "__main__":
    asyncio.run(verify_persistence())
