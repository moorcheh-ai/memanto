"""
Memory Retrieval Benchmark Suite

This module implements a comprehensive, production-grade benchmarking framework for comparing
memory retrieval accuracy and latency across multiple frameworks. It evaluates the core tension
of 2026 agent infrastructure: Accuracy vs. Resource Footprint.

Supported frameworks:
- Memanto (active companion agent with serverless retrieval optimized by moorcheh.ai)
- Mem0 (dedicated agentic memory framework)

Key Features:
- Configurable context window sizes and query patterns
- Comprehensive metrics collection (accuracy, latency, token efficiency, memory usage)
- Statistical analysis with percentile calculations
- Automated result visualization and reporting
- Robust error handling and input validation
- Production-quality logging and monitoring
- Thread-safe operations with proper resource management
- Comprehensive security validation and sanitization
"""

import time
import json
import logging
import statistics
import hashlib
import os
import sys
import gc
import psutil
import signal
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Union, Generator, Callable, TypeVar, Generic
from enum import Enum, auto
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps, lru_cache
from contextlib import contextmanager, suppress
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from threading import Lock, RLock, Event, Thread
from queue import Queue, Empty, Full
from abc import ABC, abstractmethod
from collections import defaultdict, deque
import traceback
import warnings

import numpy as np
from numpy.typing import NDArray
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for production
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
import seaborn as sns
from scipy import stats as scipy_stats

# Configure production logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('benchmark.log'),
        logging.handlers.RotatingFileHandler(
            'benchmark_detailed.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
    ]
)
logger = logging.getLogger(__name__)

# Suppress non-critical warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')

T = TypeVar('T')
R = TypeVar('R')


class BenchmarkError(Exception):
    """Base exception for benchmark operations."""
    pass

class FrameworkInitializationError(BenchmarkError):
    """Raised when framework initialization fails."""
    pass

class StorageError(BenchmarkError):
    """Raised when memory storage operations fail."""
    pass

class RetrievalError(BenchmarkError):
    """Raised when memory retrieval operations fail."""
    pass

class ValidationError(BenchmarkError):
    """Raised when input validation fails."""
    pass

class TimeoutError(BenchmarkError):
    """Raised when an operation times out."""
    pass

class ResourceExhaustionError(BenchmarkError):
    """Raised when system resources are exhausted."""
    pass

class ConfigurationError(BenchmarkError):
    """Raised when configuration is invalid."""
    pass


class FrameworkType(Enum):
    """Supported memory frameworks for benchmarking."""
    MEMANTO = "memanto"
    MEM0 = "mem0"

    @classmethod
    def from_string(cls, value: str) -> 'FrameworkType':
        """Create FrameworkType from string with validation."""
        if not isinstance(value, str):
            raise ValidationError(f"Framework type must be a string, got {type(value).__name__}")
        
        value = value.strip().lower()
        if not value:
            raise ValidationError("Framework type cannot be empty")
        
        try:
            return cls(value)
        except ValueError:
            valid_options = [e.value for e in cls]
            raise ValidationError(
                f"Invalid framework type: '{value}'. "
                f"Valid options: {valid_options}"
            )


class QueryPattern(Enum):
    """Query patterns to test different retrieval scenarios."""
    EXACT_MATCH = auto()
    SEMANTIC_SIMILARITY = auto()
    TEMPORAL_RECENCY = auto()
    COMPOSITE = auto()

    @classmethod
    def from_string(cls, value: str) -> 'QueryPattern':
        """Create QueryPattern from string with validation."""
        if not isinstance(value, str):
            raise ValidationError(f"Query pattern must be a string, got {type(value).__name__}")
        
        value = value.strip().upper()
        if not value:
            raise ValidationError("Query pattern cannot be empty")
        
        try:
            return cls[value]
        except KeyError:
            valid_options = [e.name for e in cls]
            raise ValidationError(
                f"Invalid query pattern: '{value}'. "
                f"Valid options: {valid_options}"
            )


@dataclass(frozen=True)
class BenchmarkConfig:
    """Immutable configuration for memory retrieval benchmark.
    
    Attributes:
        context_window_sizes: List of context window sizes to test
        query_patterns: List of query patterns to evaluate
        num_test_queries: Number of test queries per configuration
        num_trials: Number of trials for statistical significance
        memory_store_size: Number of memories to store
        similarity_threshold: Threshold for considering a match (0.0 to 1.0)
        output_dir: Directory for benchmark results
        frameworks: List of frameworks to benchmark
        max_workers: Maximum number of parallel workers
        timeout_seconds: Timeout for individual operations
        memory_limit_mb: Maximum memory usage limit
        enable_gc: Whether to enable garbage collection between trials
        log_level: Logging level for benchmark operations
    """
    context_window_sizes: Tuple[int, ...] = (1024, 2048, 4096, 8192)
    query_patterns: Tuple[QueryPattern, ...] = tuple(QueryPattern)
    num_test_queries: int = 100
    num_trials: int = 5
    memory_store_size: int = 1000
    similarity_threshold: float = 0.7
    output_dir: str = "./benchmark_results"
    frameworks: Tuple[FrameworkType, ...] = (FrameworkType.MEMANTO, FrameworkType.MEM0)
    max_workers: int = 4
    timeout_seconds: float = 30.0
    memory_limit_mb: float = 1024.0
    enable_gc: bool = True
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate configuration after initialization with comprehensive checks."""
        self._validate_numeric_params()
        self._validate_string_params()
        self._validate_collections()
        self._validate_frameworks()
        self._validate_output_dir()

    def _validate_numeric_params(self) -> None:
        """Validate numeric configuration parameters."""
        numeric_params = {
            'num_test_queries': (self.num_test_queries, 1, 100000),
            'num_trials': (self.num_trials, 1, 100),
            'memory_store_size': (self.memory_store_size, 1, 1000000),
            'max_workers': (self.max_workers, 1, 64),
            'timeout_seconds': (self.timeout_seconds, 0.1, 3600.0),
            'memory_limit_mb': (self.memory_limit_mb, 64.0, 65536.0),
        }
        
        for name, (value, min_val, max_val) in numeric_params.items():
            if not isinstance(value, (int, float)):
                raise ValidationError(f"{name} must be numeric, got {type(value).__name__}")
            if value < min_val or value > max_val:
                raise ValidationError(
                    f"{name} must be between {min_val} and {max_val}, got {value}"
                )
        
        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ValidationError(
                f"similarity_threshold must be between 0 and 1, got {self.similarity_threshold}"
            )

    def _validate_string_params(self) -> None:
        """Validate string configuration parameters."""
        if not isinstance(self.output_dir, str):
            raise ValidationError(f"output_dir must be a string, got {type(self.output_dir).__name__}")
        
        valid_log_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if self.log_level.upper() not in valid_log_levels:
            raise ValidationError(
                f"Invalid log_level: '{self.log_level}'. "
                f"Valid options: {valid_log_levels}"
            )

    def _validate_collections(self) -> None:
        """Validate collection configuration parameters."""
        if not self.context_window_sizes:
            raise ValidationError("context_window_sizes cannot be empty")
        
        if not self.query_patterns:
            raise ValidationError("query_patterns cannot be empty")
        
        for size in self.context_window_sizes:
            if not isinstance(size, int) or size <= 0:
                raise ValidationError(
                    f"Invalid context window size: {size}. Must be positive integer"
                )

    def _validate_frameworks(self) -> None:
        """Validate framework configuration."""
        if not self.frameworks:
            raise ValidationError("frameworks cannot be empty")
        
        for framework in self.frameworks:
            if not isinstance(framework, FrameworkType):
                raise ValidationError(
                    f"Invalid framework type: {framework}. Must be FrameworkType enum"
                )

    def _validate_output_dir(self) -> None:
        """Validate and create output directory if needed."""
        try:
            output_path = Path(self.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Verify write permissions
            test_file = output_path / '.write_test'
            test_file.touch()
            test_file.unlink()
            
        except PermissionError:
            raise ValidationError(
                f"No write permission for output directory: {self.output_dir}"
            )
        except OSError as e:
            raise ValidationError(
                f"Failed to create output directory {self.output_dir}: {e}"
            )


@dataclass
class BenchmarkMetrics:
    """Container for benchmark metrics with computed statistics."""
    accuracy: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    token_efficiency: float = 0.0
    memory_usage_mb: float = 0.0
    throughput_qps: float = 0.0
    std_dev_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    median_accuracy: float = 0.0
    accuracy_std_dev: float = 0.0
    latency_cv: float = 0.0  # Coefficient of variation

    def to_dict(self) -> Dict[str, float]:
        """Convert metrics to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_raw_data(cls, 
                     latencies: List[float], 
                     accuracies: List[float],
                     token_efficiency: float,
                     memory_usage_mb: float) -> 'BenchmarkMetrics':
        """Compute metrics from raw measurement data with robust statistics."""
        if not latencies:
            raise ValidationError("Cannot compute metrics from empty latency data")
        if not accuracies:
            raise ValidationError("Cannot compute metrics from empty accuracy data")
        
        # Validate input data
        for latency in latencies:
            if not isinstance(latency, (int, float)) or latency < 0:
                raise ValidationError(f"Invalid latency value: {latency}")
        
        for accuracy in accuracies:
            if not isinstance(accuracy, (int, float)) or not 0 <= accuracy <= 1:
                raise ValidationError(f"Invalid accuracy value: {accuracy}")
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        # Calculate percentiles using numpy for precision
        latencies_array = np.array(sorted_latencies)
        
        mean_latency = float(np.mean(latencies_array))
        std_latency = float(np.std(latencies_array)) if len(latencies) > 1 else 0.0
        
        return cls(
            accuracy=float(np.mean(accuracies)),
            median_accuracy=float(np.median(accuracies)),
            accuracy_std_dev=float(np.std(accuracies)) if len(accuracies) > 1 else 0.0,
            p50_latency_ms=float(np.percentile(latencies_array, 50)),
            p95_latency_ms=float(np.percentile(latencies_array, 95)),
            p99_latency_ms=float(np.percentile(latencies_array, 99)),
            token_efficiency=float(token_efficiency),
            memory_usage_mb=float(memory_usage_mb),
            throughput_qps=len(latencies) / (sum(latencies) / 1000) if latencies else 0.0,
            std_dev_latency_ms=std_latency,
            min_latency_ms=float(sorted_latencies[0]),
            max_latency_ms=float(sorted_latencies[-1]),
            latency_cv=std_latency / mean_latency if mean_latency > 0 else 0.0
        )


@dataclass
class BenchmarkResult:
    """Complete benchmark result for a single configuration."""
    framework: FrameworkType
    context_window_size: int
    query_pattern: QueryPattern
    metrics: BenchmarkMetrics
    raw_latencies: List[float] = field(default_factory=list)
    raw_accuracies: List[float] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    config_hash: str = field(default_factory=str)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Generate configuration hash after initialization."""
        if not self.config_hash:
            config_str = f"{self.framework.value}_{self.context_window_size}_{self.query_pattern.name}_{self.timestamp}"
            self.config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
        
        # Validate data integrity
        if self.raw_latencies and len(self.raw_latencies) != len(self.raw_accuracies):
            raise ValidationError(
                f"Mismatched data lengths: {len(self.raw_latencies)} latencies vs "
                f"{len(self.raw_accuracies)} accuracies"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            'framework': self.framework.value,
            'context_window_size': self.context_window_size,
            'query_pattern': self.query_pattern.name,
            'metrics': self.metrics.to_dict(),
            'timestamp': self.timestamp,
            'config_hash': self.config_hash,
            'metadata': self.metadata,
            'num_samples': len(self.raw_latencies)
        }

    def save(self, filepath: Union[str, Path]) -> None:
        """Save result to JSON file with error handling."""
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
            
            logger.debug(f"Saved benchmark result to {filepath}")
            
        except (IOError, OSError) as e:
            raise StorageError(f"Failed to save benchmark result to {filepath}: {e}")

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> 'BenchmarkResult':
        """Load benchmark result from JSON file."""
        try:
            filepath = Path(filepath)
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Reconstruct objects from serialized data
            framework = FrameworkType.from_string(data['framework'])
            query_pattern = QueryPattern.from_string(data['query_pattern'])
            metrics = BenchmarkMetrics(**data['metrics'])
            
            return cls(
                framework=framework,
                context_window_size=data['context_window_size'],
                query_pattern=query_pattern,
                metrics=metrics,
                timestamp=data.get('timestamp', datetime.now().isoformat()),
                config_hash=data.get('config_hash', ''),
                metadata=data.get('metadata', {})
            )
            
        except (IOError, OSError, json.JSONDecodeError, KeyError) as e:
            raise StorageError(f"Failed to load benchmark result from {filepath}: {e}")


class MemoryFrameworkAdapter(ABC):
    """Abstract base class for memory framework adapters.
    
    Provides a standardized interface for interacting with different memory frameworks,
    ensuring consistent benchmarking across implementations.
    """
    
    def __init__(self, framework_type: FrameworkType, config: BenchmarkConfig) -> None:
        """Initialize the framework adapter.
        
        Args:
            framework_type: Type of memory framework
            config: Benchmark configuration
            
        Raises:
            FrameworkInitializationError: If initialization fails
            ValidationError: If parameters are invalid
        """
        if not isinstance(framework_type, FrameworkType):
            raise ValidationError(f"framework_type must be FrameworkType, got {type(framework_type).__name__}")
        if not isinstance(config, BenchmarkConfig):
            raise ValidationError(f"config must be BenchmarkConfig, got {type(config).__name__}")
        
        self.framework_type = framework_type
        self.config = config
        self._initialized = False
        self._lock = RLock()
        self._metrics_lock = Lock()
        self._operation_count = 0
        self._error_count = 0
        self._total_latency = 0.0
        
        logger.info(f"Initializing {framework_type.value} adapter")

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the memory framework.
        
        Raises:
            FrameworkInitializationError: If initialization fails
        """
        pass

    @abstractmethod
    def store_memory(self, content