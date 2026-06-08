#!/usr/bin/env python3
"""
Benchmark runner for cross-framework memory system comparisons.
Compares Memanto against Mem0 for accuracy vs. resource footprint.
"""

import argparse
import json
import logging
import os
import sys
import time
import hashlib
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Generator, Iterator
from contextlib import contextmanager
from enum import Enum

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for CI/headless
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

# Mem0 imports
try:
    from mem0 import MemoryClient as Mem0Client
    from mem0.exceptions import Mem0APIError, Mem0AuthError, Mem0RateLimitError
except ImportError:
    Mem0Client = None  # type: ignore
    Mem0APIError = Exception
    Mem0AuthError = Exception
    Mem0RateLimitError = Exception

# Memanto imports (assumed installed)
try:
    from memanto import MemantoClient
    from memanto.exceptions import MemantoAPIError, MemantoAuthError, MemantoRateLimitError
except ImportError:
    MemantoClient = None  # type: ignore
    MemantoAPIError = Exception
    MemantoAuthError = Exception
    MemantoRateLimitError = Exception

# Configure logging with proper levels and format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cross_framework_benchmark")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class BenchmarkError(Exception):
    """Base exception for benchmark errors."""
    pass

class ConfigurationError(BenchmarkError):
    """Raised when configuration is invalid."""
    pass

class FrameworkError(BenchmarkError):
    """Raised when framework operation fails."""
    pass

class DataGenerationError(BenchmarkError):
    """Raised when test data generation fails."""
    pass

class ValidationError(BenchmarkError):
    """Raised when input validation fails."""
    pass

class TimeoutError(BenchmarkError):
    """Raised when operation times out."""
    pass

class RetryExhaustedError(BenchmarkError):
    """Raised when all retry attempts are exhausted."""
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FrameworkType(Enum):
    """Supported framework types."""
    MEMANTO = "memanto"
    MEM0 = "mem0"
    
    @classmethod
    def from_string(cls, value: str) -> "FrameworkType":
        """Create FrameworkType from string with validation.
        
        Args:
            value: Framework name string
            
        Returns:
            FrameworkType enum value
            
        Raises:
            ConfigurationError: If value is not a valid framework
        """
        try:
            return cls(value.lower())
        except ValueError:
            raise ConfigurationError(
                f"Invalid framework: {value}. Must be one of: {[e.value for e in cls]}"
            )


class MetricType(Enum):
    """Types of metrics collected during benchmarking."""
    ACCURACY = "accuracy"
    LATENCY = "latency"
    TOKEN_USAGE = "token_usage"
    MEMORY_FOOTPRINT = "memory_footprint"
    THROUGHPUT = "throughput"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for a single benchmark run.
    
    Attributes:
        framework: Name of the framework to benchmark ("memanto" or "mem0")
        num_iterations: Number of test iterations to run
        context_size: Number of previous turns to recall
        max_tokens: Maximum tokens for response generation
        api_key: API key for Memanto (optional)
        mem0_api_key: API key for Mem0 (optional)
        mem0_user_id: User ID for Mem0 session
        mem0_agent_id: Agent ID for Mem0 session
        mem0_run_id: Run ID for Mem0 session
        output_dir: Directory for benchmark results
        random_seed: Seed for reproducible test data generation
        timeout_seconds: Maximum time per iteration in seconds
        retry_attempts: Number of retry attempts for failed iterations
        batch_size: Number of concurrent requests (if supported)
        warmup_iterations: Number of warmup iterations before measurement
    """
    framework: str
    num_iterations: int = 50
    context_size: int = 3
    max_tokens: int = 512
    api_key: Optional[str] = None
    mem0_api_key: Optional[str] = None
    mem0_user_id: str = "benchmark_user"
    mem0_agent_id: str = "benchmark_agent"
    mem0_run_id: str = "benchmark_run"
    output_dir: str = "./benchmark_results"
    random_seed: int = 42
    timeout_seconds: float = 30.0
    retry_attempts: int = 3
    batch_size: int = 1
    warmup_iterations: int = 5

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Validate framework
        FrameworkType.from_string(self.framework)
        
        # Validate numeric parameters
        if self.num_iterations < 1:
            raise ConfigurationError(f"num_iterations must be >= 1, got {self.num_iterations}")
        if self.context_size < 1:
            raise ConfigurationError(f"context_size must be >= 1, got {self.context_size}")
        if self.max_tokens < 1:
            raise ConfigurationError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.timeout_seconds <= 0:
            raise ConfigurationError(f"timeout_seconds must be > 0, got {self.timeout_seconds}")
        if self.retry_attempts < 0:
            raise ConfigurationError(f"retry_attempts must be >= 0, got {self.retry_attempts}")
        if self.batch_size < 1:
            raise ConfigurationError(f"batch_size must be >= 1, got {self.batch_size}")
        if self.warmup_iterations < 0:
            raise ConfigurationError(f"warmup_iterations must be >= 0, got {self.warmup_iterations}")
        
        # Validate API keys
        if self.api_key is not None:
            sanitize_api_key(self.api_key)
        if self.mem0_api_key is not None:
            sanitize_api_key(self.mem0_api_key)


@dataclass
class BenchmarkResult:
    """Stores results from a single benchmark run.
    
    Attributes:
        framework: Name of the framework tested
        accuracy: Accuracy score (0-1)
        avg_latency_ms: Average latency in milliseconds
        p95_latency_ms: 95th percentile latency in milliseconds
        token_usage: Total token usage
        memory_footprint_mb: Memory footprint in MB
        num_iterations: Number of successful iterations
        config: Configuration used for the benchmark
        timestamp: ISO timestamp of when the benchmark was run
        throughput: Requests per second
        error_rate: Fraction of failed requests
    """
    framework: str
    accuracy: float
    avg_latency_ms: float
    p95_latency_ms: float
    token_usage: int
    memory_footprint_mb: float
    num_iterations: int
    config: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    throughput: float = 0.0
    error_rate: float = 0.0

    def __post_init__(self) -> None:
        """Validate result after initialization."""
        if not 0.0 <= self.accuracy <= 1.0:
            raise ValidationError(f"Accuracy must be between 0 and 1, got {self.accuracy}")
        if self.avg_latency_ms < 0:
            raise ValidationError(f"avg_latency_ms must be >= 0, got {self.avg_latency_ms}")
        if self.p95_latency_ms < 0:
            raise ValidationError(f"p95_latency_ms must be >= 0, got {self.p95_latency_ms}")
        if self.token_usage < 0:
            raise ValidationError(f"token_usage must be >= 0, got {self.token_usage}")
        if self.memory_footprint_mb < 0:
            raise ValidationError(f"memory_footprint_mb must be >= 0, got {self.memory_footprint_mb}")
        if self.num_iterations < 0:
            raise ValidationError(f"num_iterations must be >= 0, got {self.num_iterations}")
        if self.throughput < 0:
            raise ValidationError(f"throughput must be >= 0, got {self.throughput}")
        if not 0.0 <= self.error_rate <= 1.0:
            raise ValidationError(f"error_rate must be between 0 and 1, got {self.error_rate}")


@dataclass
class IterationMetrics:
    """Metrics collected for a single iteration.
    
    Attributes:
        iteration_number: Iteration index
        latency_ms: Request latency in milliseconds
        token_count: Number of tokens used
        memory_delta_mb: Memory usage change in MB
        success: Whether the iteration succeeded
        error_message: Error message if failed
        timestamp: When the iteration was executed
    """
    iteration_number: int
    latency_ms: float
    token_count: int
    memory_delta_mb: float
    success: bool
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# Security utilities
# ---------------------------------------------------------------------------

def sanitize_api_key(api_key: Optional[str]) -> Optional[str]:
    """Sanitize and validate API key.
    
    Args:
        api_key: Raw API key string
        
    Returns:
        Sanitized API key or None
        
    Raises:
        ValidationError: If API key format is invalid
    """
    if api_key is None:
        return None
    
    # Remove whitespace
    api_key = api_key.strip()
    
    # Basic validation
    if not api_key:
        raise ValidationError("API key cannot be empty")
    
    # Check for common injection patterns
    forbidden_patterns = ["'", "\"", ";", "--", "/*", "*/", "xp_", "DROP", "DELETE", "INSERT"]
    for pattern in forbidden_patterns:
        if pattern.lower() in api_key.lower():
            raise ValidationError(f"API key contains forbidden pattern: {pattern}")
    
    # Validate length (typical API keys are 32-128 characters)
    if not 16 <= len(api_key) <= 256:
        raise ValidationError(f"API key length must be between 16 and 256 characters, got {len(api_key)}")
    
    # Validate character set (alphanumeric and common special chars only)
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in allowed_chars for c in api_key):
        raise ValidationError("API key contains invalid characters")
    
    return api_key


def validate_file_path(path: str) -> Path:
    """Validate and sanitize file path.
    
    Args:
        path: File path string
        
    Returns:
        Validated Path object
        
    Raises:
        ValidationError: If path is invalid or contains traversal
    """
    # Check for path traversal
    if ".." in path or path.startswith("/") or path.startswith("~"):
        raise ValidationError(f"Invalid path (traversal detected): {path}")
    
    # Check for null bytes
    if "\0" in path:
        raise ValidationError("Path contains null byte")
    
    # Convert to Path and resolve
    resolved_path = Path(path).resolve()
    
    # Ensure path is within allowed directory
    allowed_base = Path.cwd()
    try:
        resolved_path.relative_to(allowed_base)
    except ValueError:
        raise ValidationError(f"Path {path} resolves outside current working directory")
    
    return resolved_path


def generate_secure_id(length: int = 32) -> str:
    """Generate a cryptographically secure random ID.
    
    Args:
        length: Length of the ID in bytes (will be hex-encoded, so 2x length)
        
    Returns:
        Hex-encoded secure random string
    """
    return secrets.token_hex(length)


# ---------------------------------------------------------------------------
# Performance utilities
# ---------------------------------------------------------------------------

@contextmanager
def measure_time() -> Generator[Dict[str, float], None, None]:
    """Context manager to measure elapsed time.
    
    Yields:
        Dictionary that will contain 'elapsed_seconds' key with the measured time
    """
    start_time = time.perf_counter()
    result: Dict[str, float] = {}
    try:
        yield result
    finally:
        result['elapsed_seconds'] = time.perf_counter() - start_time


@contextmanager
def measure_memory() -> Generator[Dict[str, float], None, None]:
    """Context manager to measure memory usage delta.
    
    Yields:
        Dictionary that will contain 'delta_mb' key with memory change in MB
    """
    import tracemalloc
    tracemalloc.start()
    result: Dict[str, float] = {}
    try:
        yield result
    finally:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result['delta_mb'] = (peak - current) / (1024 * 1024)


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0
) -> Generator[None, None, None]:
    """Generator for retry with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        
    Yields:
        None for each retry attempt
        
    Raises:
        RetryExhaustedError: If all attempts are exhausted
    """
    for attempt in range(max_attempts):
        try:
            yield
            return
        except Exception as e:
            if attempt == max_attempts - 1:
                raise RetryExhaustedError(f"All {max_attempts} attempts failed: {e}")
            
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            jitter = delay * 0.1 * (secrets.randbelow(100) / 100.0)
            total_delay = delay + jitter
            
            logger.warning(
                f"Attempt {attempt + 1}/{max_attempts} failed. "
                f"Retrying in {total_delay:.2f}s. Error: {e}"
            )
            time.sleep(total_delay)


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

class TestDataGenerator:
    """Generates test data for benchmarking memory systems.
    
    This class creates realistic conversation scenarios with known
    ground truth for accuracy evaluation.
    """
    
    def __init__(self, seed: int = 42) -> None:
        """Initialize the test data generator.
        
        Args:
            seed: Random seed for reproducibility
        """
        self.rng = np.random.default_rng(seed)
        self._initialize_templates()
    
    def _initialize_templates(self) -> None:
        """Initialize conversation templates and entities."""
        self.topics: List[str] = [
            "machine learning", "data science", "software engineering",
            "cloud computing", "cybersecurity", "artificial intelligence",
            "database systems", "networking", "operating systems",
            "web development"
        ]
        
        self.entities: Dict[str, List[str]] = {
            "person": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
            "company": ["TechCorp", "DataFlow", "CloudNine", "SecureSys", "AI Labs"],
            "project": ["Project Alpha", "Project Beta", "Project Gamma", "Project Delta"],
            "technology": ["Python", "TensorFlow", "Kubernetes", "Docker", "PostgreSQL"]
        }
        
        self.preferences: List[str] = [
            "prefers", "likes", "dislikes", "recommends", "avoids",
            "specializes in", "works on", "manages", "leads", "contributes to"
        ]
    
    def generate_conversation(self, turns: int = 5) -> List[Dict[str, str]]:
        """Generate a synthetic conversation with known facts.
        
        Args:
            turns: Number of conversation turns
            
        Returns:
            List of conversation turns with 'role' and 'content' keys
            
        Raises:
            DataGenerationError: If conversation generation fails
        """
        try:
            conversation: List[Dict[str, str]] = []
            facts: List[str] = []
            
            for i in range(turns):
                if i % 2 == 0:
                    # User turn
                    topic = self.rng.choice(self.topics)
                    entity_type = self.rng.choice(list(self.entities.keys()))
                    entity = self.rng.choice(self.entities[entity_type])
                    preference = self.rng.choice(self.preferences)
                    
                    content = f"What do you think about {entity} in {topic}? "
                    content += f"I heard they {preference} {topic}."
                    
                    conversation.append({"role": "user", "content": content})
                else:
                    # Assistant turn
                    fact = self._generate_fact()
                    facts.append(fact)
                    conversation.append({"role": "assistant", "content": fact})
            
            return conversation
            
        except Exception as e:
            raise DataGenerationError(f"Failed to generate conversation: {e}")
    
    def _generate_fact(self) -> str:
        """Generate a random fact statement.
        
        Returns:
            A fact string
        """
        entity_type = self.r