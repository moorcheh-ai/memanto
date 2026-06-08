#!/usr/bin/env python3
"""
benchmarks/reporting/generate_report.py

Generates comparison reports with scatter plots and summary tables for
Memanto vs. other memory frameworks (e.g., Mem0, Zep, Hindsight).

Usage:
    python benchmarks/reporting/generate_report.py --results <path_to_results.json> --output <output_dir>
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set, TypeVar, Generic
import hashlib
import re
from datetime import datetime
from enum import Enum

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for headless environments
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.axes import Axes

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('report_generation.log')
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPORT_STYLES: Dict[str, Any] = {
    'figure.dpi': 150,
    'figure.figsize': (12, 8),
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 11,
    'legend.fontsize': 9,
    'lines.markersize': 6,
}

VALID_METRICS: Set[str] = {
    'latency_ms', 'accuracy', 'token_cost', 'memory_mb', 
    'p95_latency_ms', 'context_window_used'
}

REQUIRED_RESULT_FIELDS: Set[str] = {
    'framework', 'test_name', 'latency_ms', 'accuracy'
}

MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB
ALLOWED_EXTENSIONS: Set[str] = {'.json'}
MAX_STRING_LENGTH: int = 100
MAX_FRAMEWORKS: int = 10
MAX_RESULTS: int = 10000

# Color scheme for different frameworks
FRAMEWORK_COLORS: Dict[str, str] = {
    'memanto': '#2196F3',
    'mem0': '#4CAF50',
    'zep': '#FF9800',
    'hindsight': '#9C27B0',
    'letta': '#F44336',
}

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------
class BenchmarkError(Exception):
    """Base exception for benchmark reporting errors."""
    pass

class ValidationError(BenchmarkError):
    """Raised when input validation fails."""
    pass

class DataIntegrityError(BenchmarkError):
    """Raised when benchmark data is corrupted or invalid."""
    pass

class ConfigurationError(BenchmarkError):
    """Raised when configuration is invalid."""
    pass

class FileProcessingError(BenchmarkError):
    """Raised when file processing fails."""
    pass

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class OutputFormat(Enum):
    """Supported output formats for reports."""
    PNG = 'png'
    PDF = 'pdf'
    SVG = 'svg'
    HTML = 'html'

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
T = TypeVar('T')
NumericArray = Union[List[float], np.ndarray]
BenchmarkData = Dict[str, List['BenchmarkResult']]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class BenchmarkResult:
    """Container for a single benchmark run result with comprehensive validation."""
    
    framework: str
    test_name: str
    latency_ms: float = 0.0
    accuracy: float = 0.0
    token_cost: float = 0.0
    memory_mb: float = 0.0
    p95_latency_ms: float = 0.0
    context_window_used: int = 0
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and sanitize input data after initialization."""
        try:
            self._validate_fields()
            self._sanitize_strings()
            self._validate_numeric_ranges()
            self._set_timestamp()
        except Exception as e:
            logger.error(f"Validation failed for BenchmarkResult: {e}")
            raise

    def _validate_fields(self) -> None:
        """Validate required fields are present and correctly typed."""
        if not isinstance(self.framework, str) or not self.framework.strip():
            raise ValidationError(f"Framework must be a non-empty string, got: {self.framework}")
        
        if not isinstance(self.test_name, str) or not self.test_name.strip():
            raise ValidationError(f"Test name must be a non-empty string, got: {self.test_name}")
        
        numeric_fields: Dict[str, Any] = {
            'latency_ms': self.latency_ms,
            'accuracy': self.accuracy,
            'token_cost': self.token_cost,
            'memory_mb': self.memory_mb,
            'p95_latency_ms': self.p95_latency_ms,
            'context_window_used': self.context_window_used,
        }
        
        for field_name, value in numeric_fields.items():
            if not isinstance(value, (int, float, np.integer, np.floating)):
                raise ValidationError(
                    f"{field_name} must be numeric, got: {type(value).__name__}"
                )
            if isinstance(value, (np.floating, np.integer)):
                value = float(value)
            if not np.isfinite(float(value)):
                raise ValidationError(f"{field_name} must be finite, got: {value}")

    def _sanitize_strings(self) -> None:
        """Sanitize string fields to prevent injection attacks."""
        self.framework = self._sanitize_string(self.framework)
        self.test_name = self._sanitize_string(self.test_name)

    @staticmethod
    def _sanitize_string(value: str) -> str:
        """
        Remove potentially dangerous characters from string.
        
        Args:
            value: Input string to sanitize
            
        Returns:
            Sanitized string with only safe characters
        """
        # Allow alphanumeric, spaces, hyphens, underscores, dots, slashes, colons
        sanitized: str = re.sub(r'[^\w\s\-_./:()]', '', value)
        return sanitized.strip()[:MAX_STRING_LENGTH]

    def _validate_numeric_ranges(self) -> None:
        """Validate numeric fields are within acceptable ranges."""
        if self.latency_ms < 0:
            raise ValidationError(f"Latency cannot be negative: {self.latency_ms}")
        
        if not 0 <= self.accuracy <= 1:
            raise ValidationError(
                f"Accuracy must be between 0 and 1, got: {self.accuracy}"
            )
        
        if self.token_cost < 0:
            raise ValidationError(f"Token cost cannot be negative: {self.token_cost}")
        
        if self.memory_mb < 0:
            raise ValidationError(f"Memory cannot be negative: {self.memory_mb}")
        
        if self.p95_latency_ms < 0:
            raise ValidationError(f"P95 latency cannot be negative: {self.p95_latency_ms}")
        
        if self.context_window_used < 0:
            raise ValidationError(
                f"Context window used cannot be negative: {self.context_window_used}"
            )

    def _set_timestamp(self) -> None:
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BenchmarkResult':
        """
        Create BenchmarkResult from dictionary with comprehensive validation.
        
        Args:
            data: Dictionary containing benchmark result fields
            
        Returns:
            Validated BenchmarkResult instance
            
        Raises:
            ValidationError: If required fields are missing or invalid
            DataIntegrityError: If data parsing fails
        """
        try:
            # Validate required fields exist
            missing_fields: Set[str] = REQUIRED_RESULT_FIELDS - set(data.keys())
            if missing_fields:
                raise ValidationError(f"Missing required fields: {missing_fields}")

            # Extract and validate each field with safe conversions
            framework: str = str(data.get('framework', 'unknown'))
            test_name: str = str(data.get('test_name', 'unnamed'))
            
            # Use safe float conversion for numeric fields
            latency_ms: float = cls._safe_float(data.get('latency_ms', 0.0), 'latency_ms')
            accuracy: float = cls._safe_float(data.get('accuracy', 0.0), 'accuracy')
            token_cost: float = cls._safe_float(data.get('token_cost', 0.0), 'token_cost')
            memory_mb: float = cls._safe_float(data.get('memory_mb', 0.0), 'memory_mb')
            p95_latency_ms: float = cls._safe_float(
                data.get('p95_latency_ms', data.get('latency_ms', 0.0)), 
                'p95_latency_ms'
            )
            context_window_used: int = cls._safe_int(
                data.get('context_window_used', 0), 
                'context_window_used'
            )
            
            # Extract optional fields
            timestamp: Optional[str] = str(data.get('timestamp', '')) if data.get('timestamp') else None
            metadata: Dict[str, Any] = data.get('metadata', {})

            return cls(
                framework=framework,
                test_name=test_name,
                latency_ms=latency_ms,
                accuracy=accuracy,
                token_cost=token_cost,
                memory_mb=memory_mb,
                p95_latency_ms=p95_latency_ms,
                context_window_used=context_window_used,
                timestamp=timestamp,
                metadata=metadata,
            )
            
        except (TypeError, ValueError) as e:
            raise DataIntegrityError(f"Failed to parse benchmark result: {e}") from e

    @staticmethod
    def _safe_float(value: Any, field_name: str) -> float:
        """
        Safely convert value to float with validation.
        
        Args:
            value: Input value to convert
            field_name: Name of the field for error messages
            
        Returns:
            Validated float value
            
        Raises:
            ValidationError: If conversion fails or value is invalid
        """
        try:
            result: float = float(value)
            if not np.isfinite(result):
                raise ValueError(f"Non-finite value: {result}")
            return result
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Invalid float value for {field_name}: {value}") from e

    @staticmethod
    def _safe_int(value: Any, field_name: str) -> int:
        """
        Safely convert value to int with validation.
        
        Args:
            value: Input value to convert
            field_name: Name of the field for error messages
            
        Returns:
            Validated integer value
            
        Raises:
            ValidationError: If conversion fails
        """
        try:
            result: int = int(float(value))
            if not np.isfinite(float(value)):
                raise ValueError(f"Non-finite value: {value}")
            return result
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Invalid int value for {field_name}: {value}") from e

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert BenchmarkResult to dictionary.
        
        Returns:
            Dictionary representation of the benchmark result
        """
        return {
            'framework': self.framework,
            'test_name': self.test_name,
            'latency_ms': self.latency_ms,
            'accuracy': self.accuracy,
            'token_cost': self.token_cost,
            'memory_mb': self.memory_mb,
            'p95_latency_ms': self.p95_latency_ms,
            'context_window_used': self.context_window_used,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class ReportConfig:
    """Configuration for report generation with validation."""
    
    results_path: Path
    output_dir: Path
    title: str = "Memory Framework Benchmark Comparison"
    output_format: OutputFormat = OutputFormat.PNG
    dpi: int = 150
    figsize: Tuple[int, int] = (12, 8)
    show_grid: bool = True
    show_legend: bool = True
    include_summary_table: bool = True
    normalize_metrics: bool = False
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self._validate_paths()
        self._validate_parameters()
    
    def _validate_paths(self) -> None:
        """Validate file paths exist and are accessible."""
        if not self.results_path.exists():
            raise ConfigurationError(f"Results file not found: {self.results_path}")
        
        if not self.results_path.is_file():
            raise ConfigurationError(f"Results path is not a file: {self.results_path}")
        
        # Create output directory if it doesn't exist
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise ConfigurationError(
                f"Cannot create output directory: {self.output_dir}"
            ) from e
    
    def _validate_parameters(self) -> None:
        """Validate configuration parameters."""
        if self.dpi < 72 or self.dpi > 600:
            raise ConfigurationError(f"DPI must be between 72 and 600, got: {self.dpi}")
        
        if not isinstance(self.figsize, tuple) or len(self.figsize) != 2:
            raise ConfigurationError(f"figsize must be a tuple of 2 integers")
        
        if any(dim < 4 or dim > 40 for dim in self.figsize):
            raise ConfigurationError(
                f"Figure dimensions must be between 4 and 40 inches"
            )


# ---------------------------------------------------------------------------
# Report Generator Class
# ---------------------------------------------------------------------------
class ReportGenerator:
    """
    Generates comprehensive benchmark comparison reports with visualizations.
    
    This class handles loading benchmark data, validating it, and generating
    various visualizations and summary tables for comparing memory frameworks.
    """
    
    def __init__(self, config: ReportConfig) -> None:
        """
        Initialize the report generator with configuration.
        
        Args:
            config: ReportConfig instance with generation parameters
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config: ReportConfig = config
        self.results: List[BenchmarkResult] = []
        self.processed_data: BenchmarkData = {}
        self._setup_plotting_style()
        logger.info(f"Initialized ReportGenerator with config: {config}")
    
    def _setup_plotting_style(self) -> None:
        """Configure matplotlib style for consistent visualizations."""
        try:
            plt.style.use('seaborn-v0_8-darkgrid')
            matplotlib.rcParams.update(REPORT_STYLES)
            matplotlib.rcParams['figure.dpi'] = self.config.dpi
            matplotlib.rcParams['figure.figsize'] = self.config.figsize
        except Exception as e:
            logger.warning(f"Failed to set plotting style, using defaults: {e}")
    
    def load_results(self) -> None:
        """
        Load and validate benchmark results from JSON file.
        
        Raises:
            FileProcessingError: If file loading fails
            DataIntegrityError: If data validation fails
        """
        file_path: Path = self.config.results_path
        
        # Validate file
        self._validate_file(file_path)
        
        try:
            # Read and parse JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data: Any = json.load(f)
            
            # Validate data structure
            if not isinstance(raw_data, list):
                raise DataIntegrityError("Results must be a JSON array")
            
            if len(raw_data) > MAX_RESULTS:
                raise DataIntegrityError(
                    f"Too many results: {len(raw_data)} (max: {MAX_RESULTS})"
                )
            
            # Parse each result
            self.results = []
            for idx, item in enumerate(raw_data):
                try:
                    if not isinstance(item, dict):
                        logger.warning(f"Skipping non-dict item at index {idx}")
                        continue
                    
                    result: BenchmarkResult = BenchmarkResult.from_dict(item)
                    self.results.append(result)
                    
                except (ValidationError, DataIntegrityError) as e:
                    logger.warning(f"Skipping invalid result at index {idx}: {e}")
                    continue
            
            if not self.results:
                raise DataIntegrityError("No valid benchmark results found")
            
            # Group results by framework
            self._group_results()
            
            logger.info(
                f"Loaded {len(self.results)} valid results from {len(self.processed_data)} frameworks"
            )
            
        except json.JSONDecodeError as e:
            raise FileProcessingError(f"Invalid JSON file: {e}") from e
        except IOError as e:
            raise FileProcessingError(f"Failed to read file: {e}") from e
    
    def _validate_file(self, file_path: Path) -> None:
        """
        Validate input file before processing.
        
        Args:
            file_path: Path to the input file
            
        Raises:
            ValidationError: If file validation fails
        """
        # Check file extension
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Invalid file extension: {file_path.suffix}. "
                f"Allowed: {ALLOWED_EXTENSIONS}"
            )
        
        # Check file size
        try:
            file_size: int = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                raise ValidationError(
                    f"File too large: {file_size} bytes (max: {MAX_FILE_SIZE_BYTES})"
                )
            if file_size == 0:
                raise ValidationError("File is empty")
        except OSError as e:
            raise ValidationError(f"Failed to check file