"""
Migration Runner Script for ChatGPT and Claude Adapters.

This script demonstrates how to run the Memanto migration CLI programmatically
on the provided sample exports. It uses the --dry-run flag to generate a preview
of the mapped memories without actually sending them to a Memanto agent.

Usage:
    python run_migration.py
"""

import subprocess
import sys
from pathlib import Path

def run_cli(provider: str, filename: str):
    print(f"\n{'='*50}")
    print(f"Running migration for {provider.upper()}")
    print(f"{'='*50}")
    
    file_path = Path(__file__).parent / filename
    
    cmd = [
        sys.executable,
        "-m", "memanto.cli.main",
        "migrate", provider,
        "--file", str(file_path),
        "--dry-run"
    ]
    
    # We must run it from the root of the project to ensure memanto module is found
    project_root = Path(__file__).parent.parent.parent.parent
    
    try:
        result = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running migration for {provider}:\n{e.stderr}")
        raise

if __name__ == "__main__":
    run_cli("chatgpt", "sample_chatgpt.json")
    run_cli("claude", "sample_claude.json")
