import os
import time
from abc import ABC, abstractmethod

class BaseMemoryLayer(ABC):
    @abstractmethod
    def add_memory(self, user_id: str, content: str) -> dict:
        """Add a memory and return metrics {"latency": float, "tokens": int}"""
        pass

    @abstractmethod
    def retrieve_memory(self, user_id: str, query: str) -> tuple[str, dict]:
        """Retrieve memory context and return (context, metrics)"""
        pass

class MemantoLayer(BaseMemoryLayer):
    def __init__(self):
        from moorcheh_sdk import MoorchehClient
        api_key = os.getenv("MOORCHEH_API_KEY")
        if not api_key:
            raise ValueError("MOORCHEH_API_KEY environment variable is not set.")
        self.client = MoorchehClient(api_key=api_key)
        self.created_namespaces = set()

        # Simple token estimation for benchmark purposes if SDK doesn't provide it
        import tiktoken
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def add_memory(self, user_id: str, content: str) -> dict:
        start_time = time.time()
        
        import uuid
        # Ensure the namespace is created before uploading
        if user_id not in self.created_namespaces:
            self.client.namespaces.create(namespace_name=user_id, type='text')
            self.created_namespaces.add(user_id)

        self.client.documents.upload(namespace_name=user_id, documents=[{"id": str(uuid.uuid4()), "text": content}])
            
        latency = time.time() - start_time
        return {"latency": latency, "tokens": self._count_tokens(content)}

    def retrieve_memory(self, user_id: str, query: str) -> tuple[str, dict]:
        start_time = time.time()
        
        res = self.client.answer.generate(query=query, namespace=user_id)
        context = res.get('answer', '') if isinstance(res, dict) else getattr(res, 'answer', '')
            
        latency = time.time() - start_time
        return context, {"latency": latency, "tokens": self._count_tokens(context)}

class Mem0Layer(BaseMemoryLayer):
    def __init__(self):
        from mem0 import Memory
        config = {
            "llm": {
                "provider": "groq",
                "config": {
                    "model": "llama-3.3-70b-versatile",
                    "temperature": 0.0,
                    "max_tokens": 1500,
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": "sentence-transformers/all-MiniLM-L6-v2"
                }
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "mem0_hf",
                    "embedding_model_dims": 384
                }
            }
        }
        self.client = Memory.from_config(config)
        
        import tiktoken
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def add_memory(self, user_id: str, content: str) -> dict:
        start_time = time.time()
        self.client.add(content, user_id=user_id)
        latency = time.time() - start_time
        return {"latency": latency, "tokens": self._count_tokens(content)}

    def retrieve_memory(self, user_id: str, query: str) -> tuple[str, dict]:
        start_time = time.time()
        results = self.client.search(query, filters={'user_id': user_id})
        
        # Format Mem0 results into a single context string
        memories = results.get("results", []) if isinstance(results, dict) else results
        context = "\n".join([res.get("memory", "") for res in memories]) if memories else ""
        
        latency = time.time() - start_time
        return context, {"latency": latency, "tokens": self._count_tokens(context)}
