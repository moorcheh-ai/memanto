from typing import Any, Dict, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
import aiohttp

class MemantoCheckpointSaver(BaseCheckpointSaver):
      def __init__(self, api_url: str, api_key: str):
                self.api_url = api_url
                self.api_key = api_key

      async def put(self, config: Dict[str, Any], checkpoint: Dict[str, Any]) -> None:
                async with aiohttp.ClientSession() as session:
                              payload = {
                                                "thread_id": config["configurable"]["thread_id"],
                                                "checkpoint": checkpoint
                              }
                              async with session.post(
                                                f"{self.api_url}/memory/write",
                                                json=payload,
                                                headers={"Authorization": f"Bearer {self.api_key}"}
                              ) as response:
                                                response.raise_for_status()

                      async def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                                thread_id = config["configurable"]["thread_id"]
                                async with aiohttp.ClientSession() as session:
                                              async with session.get(
                                                                f"{self.api_url}/memory/read/{thread_id}",
                                                                headers={"Authorization": f"Bearer {self.api_key}"}
                                              ) as response:
                                                                if response.status == 404:
                                                                                      return None
                                                                                  data = await response.json()
                                                                return data["checkpoint"]
                                                
