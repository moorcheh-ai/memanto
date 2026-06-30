"""
Backward-compatible import shim for the moved memory validation service.
"""

from memanto.app.services.memory_validation_service import (  # noqa: F401
    MemoryValidationService,
    ValidationPolicy,
)
