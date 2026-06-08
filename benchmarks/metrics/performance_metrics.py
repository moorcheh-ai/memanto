"""
benchmarks/metrics/performance_metrics.py

Production-grade metric collectors for token efficiency, p95 latency,
and preference resolution accuracy (F1 score on preference recall).

This module provides reusable metric collectors designed for benchmarking
AI agent memory frameworks in production-grade, stateful systems.
"""

import time
import statistics
import logging
from typing import List, Dict, Optional, Tuple, Any, Union, Set, Callable, TypeVar, cast
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

# Configure module logger
logger = logging.getLogger(__name__)

# Type aliases
MetricValue = Union[int, float]
MetricDict = Dict[str, MetricValue]
Timestamp = float
LatencyMs = float
TokenCount = int

# Generic type for decorator
F = TypeVar('F', bound=Callable[..., Any])


class MetricError(Exception):
    """Base exception for metric-related errors."""
    pass


class MetricValidationError(MetricError):
    """Custom exception for metric validation failures."""
    pass


class MetricComputationError(MetricError):
    """Custom exception for metric computation failures."""
    pass


class MetricPersistenceError(MetricError):
    """Custom exception for metric persistence failures."""
    pass


class MetricType(Enum):
    """Enumeration of supported metric types."""
    TOKEN_EFFICIENCY = "token_efficiency"
    LATENCY = "latency"
    PREFERENCE_RESOLUTION = "preference_resolution"


def validate_numeric(value: Any, name: str, allow_negative: bool = False) -> None:
    """Validate that a value is a valid numeric type.
    
    Args:
        value: Value to validate
        name: Name of the parameter for error messages
        allow_negative: Whether negative values are allowed
        
    Raises:
        MetricValidationError: If validation fails
    """
    if not isinstance(value, (int, float, Decimal)):
        raise MetricValidationError(
            f"{name} must be numeric, got {type(value).__name__}"
        )
    if not allow_negative and value < 0:
        raise MetricValidationError(
            f"{name} cannot be negative: {value}"
        )


def validate_positive_int(value: Any, name: str) -> None:
    """Validate that a value is a positive integer.
    
    Args:
        value: Value to validate
        name: Name of the parameter for error messages
        
    Raises:
        MetricValidationError: If validation fails
    """
    if not isinstance(value, int):
        raise MetricValidationError(
            f"{name} must be an integer, got {type(value).__name__}"
        )
    if value < 0:
        raise MetricValidationError(
            f"{name} cannot be negative: {value}"
        )


def log_metrics(func: F) -> F:
    """Decorator to log metric operations with timing.
    
    Args:
        func: Function to wrap
        
    Returns:
        Wrapped function with logging
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        func_name = func.__name__
        
        try:
            result = func(*args, **kwargs)
            elapsed = (time.perf_counter() - start_time) * 1000
            
            logger.debug(
                f"Metric operation '{func_name}' completed in {elapsed:.2f}ms"
            )
            return result
            
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Metric operation '{func_name}' failed after {elapsed:.2f}ms: {e}"
            )
            raise
            
    return cast(F, wrapper)


@dataclass
class TokenEfficiencyMetrics:
    """Metrics for token efficiency analysis.
    
    Tracks token consumption patterns across queries to evaluate
    the efficiency of memory framework token usage.
    
    Attributes:
        total_tokens_consumed: Cumulative tokens consumed across all queries
        total_queries: Total number of queries processed
        tokens_per_query: List of token counts per individual query
        avg_tokens_per_query: Mean tokens consumed per query
        median_tokens_per_query: Median tokens consumed per query
        std_tokens_per_query: Standard deviation of tokens per query
        min_tokens_per_query: Minimum tokens consumed in a single query
        max_tokens_per_query: Maximum tokens consumed in a single query
        timestamp: Timestamp of metric creation
        metadata: Additional metadata for the metrics
    """
    
    total_tokens_consumed: int = 0
    total_queries: int = 0
    tokens_per_query: List[float] = field(default_factory=list)
    avg_tokens_per_query: float = 0.0
    median_tokens_per_query: float = 0.0
    std_tokens_per_query: float = 0.0
    min_tokens_per_query: float = 0.0
    max_tokens_per_query: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate initialization parameters."""
        if self.total_tokens_consumed < 0:
            raise MetricValidationError(
                f"total_tokens_consumed cannot be negative: {self.total_tokens_consumed}"
            )
        if self.total_queries < 0:
            raise MetricValidationError(
                f"total_queries cannot be negative: {self.total_queries}"
            )
        
        # Validate tokens_per_query list
        for i, tokens in enumerate(self.tokens_per_query):
            if not isinstance(tokens, (int, float)):
                raise MetricValidationError(
                    f"tokens_per_query[{i}] must be numeric, got {type(tokens).__name__}"
                )
            if tokens < 0:
                raise MetricValidationError(
                    f"tokens_per_query[{i}] cannot be negative: {tokens}"
                )

    @log_metrics
    def update(self, tokens: TokenCount, queries: int = 1) -> None:
        """Update metrics with new token consumption data.
        
        Args:
            tokens: Number of tokens consumed
            queries: Number of queries that consumed these tokens
            
        Raises:
            MetricValidationError: If tokens or queries are invalid
        """
        validate_numeric(tokens, "tokens")
        validate_positive_int(queries, "queries")
        
        self.total_tokens_consumed += tokens
        self.total_queries += queries
        
        tokens_per_q = Decimal(str(tokens)) / Decimal(str(max(queries, 1)))
        self.tokens_per_query.append(float(tokens_per_q.quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )))
        
        logger.debug(
            f"Updated token metrics: tokens={tokens}, queries={queries}, "
            f"tokens_per_q={tokens_per_q:.2f}"
        )

    @log_metrics
    def compute(self) -> MetricDict:
        """Compute final aggregated token efficiency metrics.
        
        Returns:
            Dictionary containing all computed token efficiency metrics
            
        Raises:
            MetricComputationError: If computation fails
        """
        try:
            if not self.tokens_per_query:
                logger.warning("No token data available for computation")
                return self._get_empty_result()

            # Use numpy for efficient computation
            tokens_array: NDArray[np.float64] = np.array(
                self.tokens_per_query, dtype=np.float64
            )
            
            self.avg_tokens_per_query = float(np.mean(tokens_array))
            self.median_tokens_per_query = float(np.median(tokens_array))
            self.std_tokens_per_query = float(np.std(tokens_array))
            self.min_tokens_per_query = float(np.min(tokens_array))
            self.max_tokens_per_query = float(np.max(tokens_array))

            result = self._format_result()
            
            logger.info(f"Computed token efficiency metrics: {result}")
            return result
            
        except Exception as e:
            raise MetricComputationError(
                f"Failed to compute token efficiency metrics: {e}"
            ) from e

    def _get_empty_result(self) -> MetricDict:
        """Get empty result when no data is available.
        
        Returns:
            Dictionary with zeroed metrics
        """
        return {
            "avg_tokens_per_query": 0.0,
            "median_tokens_per_query": 0.0,
            "std_tokens_per_query": 0.0,
            "min_tokens_per_query": 0.0,
            "max_tokens_per_query": 0.0,
            "total_tokens_consumed": 0,
            "total_queries": 0,
            "timestamp": self.timestamp.isoformat(),
        }

    def _format_result(self) -> MetricDict:
        """Format computed metrics with proper rounding.
        
        Returns:
            Dictionary with formatted metrics
        """
        return {
            "avg_tokens_per_query": round(self.avg_tokens_per_query, 2),
            "median_tokens_per_query": round(self.median_tokens_per_query, 2),
            "std_tokens_per_query": round(self.std_tokens_per_query, 2),
            "min_tokens_per_query": round(self.min_tokens_per_query, 2),
            "max_tokens_per_query": round(self.max_tokens_per_query, 2),
            "total_tokens_consumed": self.total_tokens_consumed,
            "total_queries": self.total_queries,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self) -> str:
        """Serialize metrics to JSON.
        
        Returns:
            JSON string representation of metrics
            
        Raises:
            MetricPersistenceError: If serialization fails
        """
        try:
            data = asdict(self)
            data['timestamp'] = self.timestamp.isoformat()
            return json.dumps(data, indent=2)
        except Exception as e:
            raise MetricPersistenceError(
                f"Failed to serialize metrics to JSON: {e}"
            ) from e

    @classmethod
    def from_json(cls, json_str: str) -> 'TokenEfficiencyMetrics':
        """Deserialize metrics from JSON.
        
        Args:
            json_str: JSON string to deserialize
            
        Returns:
            TokenEfficiencyMetrics instance
            
        Raises:
            MetricPersistenceError: If deserialization fails
        """
        try:
            data = json.loads(json_str)
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            return cls(**data)
        except Exception as e:
            raise MetricPersistenceError(
                f"Failed to deserialize metrics from JSON: {e}"
            ) from e


@dataclass
class P95LatencyMetrics:
    """Metrics for p95 latency analysis.
    
    Tracks request latencies to evaluate the performance characteristics
    of memory framework operations.
    
    Attributes:
        latencies: List of recorded latency measurements in milliseconds
        p95_latency: 95th percentile latency
        avg_latency: Mean latency
        median_latency: Median latency
        min_latency: Minimum latency
        max_latency: Maximum latency
        std_latency: Standard deviation of latencies
        timestamp: Timestamp of metric creation
        metadata: Additional metadata for the metrics
    """
    
    latencies: List[float] = field(default_factory=list)
    p95_latency: float = 0.0
    avg_latency: float = 0.0
    median_latency: float = 0.0
    min_latency: float = 0.0
    max_latency: float = 0.0
    std_latency: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate initialization parameters."""
        for i, latency in enumerate(self.latencies):
            if not isinstance(latency, (int, float)):
                raise MetricValidationError(
                    f"latencies[{i}] must be numeric, got {type(latency).__name__}"
                )
            if latency < 0:
                raise MetricValidationError(
                    f"latencies[{i}] cannot be negative: {latency}"
                )

    @log_metrics
    def record_latency(self, latency_ms: LatencyMs) -> None:
        """Record a single latency measurement in milliseconds.
        
        Args:
            latency_ms: Latency measurement in milliseconds
            
        Raises:
            MetricValidationError: If latency_ms is invalid
        """
        validate_numeric(latency_ms, "latency_ms")
        
        self.latencies.append(latency_ms)
        logger.debug(f"Recorded latency: {latency_ms:.2f}ms")

    @log_metrics
    def compute(self) -> MetricDict:
        """Compute p95 and other latency statistics.
        
        Returns:
            Dictionary containing all computed latency metrics
            
        Raises:
            MetricComputationError: If computation fails
        """
        try:
            if not self.latencies:
                logger.warning("No latency data available for computation")
                return self._get_empty_result()

            # Use numpy for efficient computation
            latencies_array: NDArray[np.float64] = np.array(
                self.latencies, dtype=np.float64
            )
            
            self.p95_latency = float(np.percentile(latencies_array, 95))
            self.avg_latency = float(np.mean(latencies_array))
            self.median_latency = float(np.median(latencies_array))
            self.min_latency = float(np.min(latencies_array))
            self.max_latency = float(np.max(latencies_array))
            self.std_latency = float(np.std(latencies_array))

            result = self._format_result()
            
            logger.info(f"Computed latency metrics: {result}")
            return result
            
        except Exception as e:
            raise MetricComputationError(
                f"Failed to compute latency metrics: {e}"
            ) from e

    def _get_empty_result(self) -> MetricDict:
        """Get empty result when no data is available.
        
        Returns:
            Dictionary with zeroed metrics
        """
        return {
            "p95_latency": 0.0,
            "avg_latency": 0.0,
            "median_latency": 0.0,
            "min_latency": 0.0,
            "max_latency": 0.0,
            "std_latency": 0.0,
            "total_requests": 0,
            "timestamp": self.timestamp.isoformat(),
        }

    def _format_result(self) -> MetricDict:
        """Format computed metrics with proper rounding.
        
        Returns:
            Dictionary with formatted metrics
        """
        return {
            "p95_latency": round(self.p95_latency, 2),
            "avg_latency": round(self.avg_latency, 2),
            "median_latency": round(self.median_latency, 2),
            "min_latency": round(self.min_latency, 2),
            "max_latency": round(self.max_latency, 2),
            "std_latency": round(self.std_latency, 2),
            "total_requests": len(self.latencies),
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self) -> str:
        """Serialize metrics to JSON.
        
        Returns:
            JSON string representation of metrics
            
        Raises:
            MetricPersistenceError: If serialization fails
        """
        try:
            data = asdict(self)
            data['timestamp'] = self.timestamp.isoformat()
            return json.dumps(data, indent=2)
        except Exception as e:
            raise MetricPersistenceError(
                f"Failed to serialize metrics to JSON: {e}"
            ) from e

    @classmethod
    def from_json(cls, json_str: str) -> 'P95LatencyMetrics':
        """Deserialize metrics from JSON.
        
        Args:
            json_str: JSON string to deserialize
            
        Returns:
            P95LatencyMetrics instance
            
        Raises:
            MetricPersistenceError: If deserialization fails
        """
        try:
            data = json.loads(json_str)
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            return cls(**data)
        except Exception as e:
            raise MetricPersistenceError(
                f"Failed to deserialize metrics from JSON: {e}"
            ) from e


@dataclass
class PreferenceResolutionMetrics:
    """Metrics for preference resolution accuracy.
    
    Evaluates the accuracy of preference recall using F1 score,
    precision, and recall metrics.
    
    Attributes:
        true_positives: Number of correctly recalled preferences
        false_positives: Number of incorrectly recalled preferences
        false_negatives: Number of missed preferences
        true_negatives: Number of correctly excluded non-preferences
        precision: Precision score
        recall: Recall score
        f1_score: F1 score
        timestamp: Timestamp of metric creation
        metadata: Additional metadata for the metrics
    """
    
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate initialization parameters."""
        for field_name in ['true_positives', 'false_positives', 
                          'false_negatives', 'true_negatives']:
            value = getattr(self, field_name)
            if not isinstance(value, int):
                raise MetricValidationError(
                    f"{field_name} must be an integer, got {type(value).__name__}"
                )
            if value < 0:
                raise MetricValidationError(
                    f"{field_name} cannot be negative: {value}"
                )

    @log_metrics
    def update(self, 
               true_positives: int