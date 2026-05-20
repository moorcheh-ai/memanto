"""MEMANTO application package."""

try:
    from ._version import __version__
except ModuleNotFoundError:
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
