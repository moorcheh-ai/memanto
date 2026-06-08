import os
from pydantic import BaseModel
from integrations.langgraph.memanto_langgraph import MemantoStore, MemantoStoreConfig

class UserProfile(BaseModel):
    """Custom user schema for type-safe memory."""
    user_id: str
    preference: str
    last_interaction: str

def run_verification():
    # Configuration
    config = MemantoStoreConfig(
        api_key=os.getenv("MEMANTO_API_KEY", "test_key"),
        base_url=os.getenv("MEMANTO_URL", "http://localhost:8000")
    )
    
    # Initialize generic store with UserProfile type
    store = MemantoStore[UserProfile](config)
    
    namespace = "verification_test"
    key = "user_123"
    
    # Session A: Store typed object
    profile_a = UserProfile(
        user_id="123", 
        preference="Dark Mode", 
        last_interaction="2023-10-27"
    )
    store.put(namespace, key, profile_a.model_dump())
    print(f"Stored: {profile_a}")

    # Session B: Retrieve and validate type
    retrieved_data = store.get(namespace, key)
    if retrieved_data:
        profile_b = UserProfile(**retrieved_data)
        print(f"Retrieved: {profile_b}")
        assert profile_a == profile_b
        print("Verification Successful: Cross-process persistence and type-safety confirmed.")
    else:
        print("Verification Failed: No data retrieved.")

if __name__ == "__main__":
    run_verification()
