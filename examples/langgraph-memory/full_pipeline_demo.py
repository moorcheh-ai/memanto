import asyncio
from pydantic import BaseModel, Field
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_langgraph import MemantoStore

class UserPreference(BaseModel):
    """Schema for user-specific preferences."""
    theme: str
    notifications_enabled: bool
    preferred_language: str

async def run_session(session_id: int, sdk_client: SdkClient, store: MemantoStore, action: str, value: str = None):
    agent_id = "user_123"
    namespace = (agent_id,)
    key = "preferences"

    if action == "write":
        pref = UserPreference(theme=value, notifications_enabled=True, preferred_language="English")
        await store.put(namespace, key, pref)
        print(f"Session {session_id}: Saved preference {value}")
    
    elif action == "read":
        pref = await store.get(namespace, key)
        print(f"Session {session_id}: Retrieved preference: {pref.theme if pref else 'None'}")

async def main():
    # Initialize SDK and Store
    sdk = SdkClient()
    store = MemantoStore(sdk_client=sdk, schema_type=UserPreference)

    print("--- Session 1: Writing Memory ---")
    await run_session(1, sdk, store, "write", "dark-mode")

    print("\n--- Session 2: Reading Memory (Cross-Process Simulation) ---")
    # Re-instantiate to simulate a new process/thread
    sdk_new = SdkClient()
    store_new = MemantoStore(sdk_client=sdk_new, schema_type=UserPreference)
    await run_session(2, sdk_new, store_new, "read")

if __name__ == "__main__":
    asyncio.run(main())
