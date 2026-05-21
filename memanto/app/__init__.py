"""MEMANTO application package."""

try:
    from ._version import __version__
except ModuleNotFoundError as exc:
    if exc.name == "memanto.app._version":
        __version__ = "0.0.0+local"
    else:
        raise

__all__ = ["__version__"]
