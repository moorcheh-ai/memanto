import asyncio

class BatchProcessor:
    def __init__(self, batch_size=10, interval=0.1):
        self.batch_size = batch_size
        self.interval = interval
        self.queue = []
    async def add(self, item):
        self.queue.append(item)
        if len(self.queue) >= self.batch_size:
            return await self.flush()
        return None
    async def flush(self):
        batch = self.queue[:self.batch_size]
        self.queue = self.queue[self.batch_size:]
        return {"processed": len(batch)}