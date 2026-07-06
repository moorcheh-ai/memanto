import asyncio
from memanto import MemantoAgent

async def poc():
    agent = MemantoAgent(api_key='test_key')
    # Simulate rapid memory storage with identical timestamps
    for i in range(5):
        await agent.memorize(f"Event {i} at same time", timestamp=1234567890.0)
    # Retrieve relevant memories
    memories = await agent.recall("Event 2")
    print("Retrieved:", memories)
    # Expected: Event 2 at index 2, but often returns wrong event

if __name__ == "__main__":
    asyncio.run(poc())