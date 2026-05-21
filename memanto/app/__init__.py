"""MEMANTO application package."""


def _load_version() -> str:
    """Return the packaged version or a local source-tree fallback."""

    try:
        from ._version import __version__ as version
    except ModuleNotFoundError as exc:
        if exc.name == "memanto.app._version":
            return "0.0.0+local"
        raise
    return version


__version__ = _load_version()

__all__ = ["__version__"]
