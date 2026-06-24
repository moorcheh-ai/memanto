"""Memanto memory-agent provider for the Hermes agent.

Install the directory plugin with the bundled console script::

    hermes-memanto-install

Then point Hermes at it::

    hermes config set memory.provider memanto
"""

from hermes_memanto.provider import MemantoMemoryProvider, register

__all__ = ["MemantoMemoryProvider", "register"]
__version__ = "0.1.0"
