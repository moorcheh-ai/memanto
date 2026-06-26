"""Configuration for Memanto client."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MemantoConfig:
    """Configuration for Memanto client.
    
    Attributes:
        api_key: Moorcheh API key. Defaults to MOORCHEH_API_KEY env var.
        base_url: Moorcheh API base URL.
        timeout: Request timeout in seconds.
        rate_limit_seconds: Minimum seconds between requests.
        max_content_length: Maximum memory content length in characters.
    """
    
    api_key: str = ""
    base_url: str = "https://api.moorcheh.ai/v1"
    timeout: int = 30
    rate_limit_seconds: float = 0.1
    max_content_length: int = 100_000
    
    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.getenv("MOORCHEH_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY environment variable must be set"
            )