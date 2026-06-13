from benchmark.frameworks.base import MemoryFramework
from benchmark.frameworks.memanto_adapter import MemantoAdapter

__all__ = ["MemoryFramework", "MemantoAdapter"]

# Optional adapters (frameworks may not be installed)
try:
    from benchmark.frameworks.mem0_adapter import Mem0Adapter
    __all__.append("Mem0Adapter")
except ImportError:
    pass

try:
    from benchmark.frameworks.zep_adapter import ZepAdapter
    __all__.append("ZepAdapter")
except ImportError:
    pass