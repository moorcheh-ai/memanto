"""
MEMANTO CLI - Main Entry Point

Command-line interface for MEMANTO V2 API
"""

# Import the app instance from shared module
# Import commands package to trigger registration of all CLI commands
import memanto.cli.commands  # noqa: F401
from memanto.cli.commands._shared import app

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    app()
