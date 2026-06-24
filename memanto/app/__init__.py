"""MEMANTO application package."""

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
