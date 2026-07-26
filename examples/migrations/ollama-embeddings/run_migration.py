"""
Single-command entry point for the Ollama → Memanto migration.

Usage:
    python run_migration.py --model nomic-embed-text --context "Some memory text"
    python run_migration.py --model all-minilm --context-file contexts.txt
    python run_migration.py --dry-run
    python run_migration.py --model nomic-embed-text --chat-model llama3.2 \\
        --context "User likes dark mode" --output-dir ./my_migration

Outputs:
    ollama_export.json  — ready for `memanto migrate --file`
    okf_bundle/         — portable OKF directory for `memanto migrate okf`
"""

if __name__ == "__main__":
    from adapter.ollama_adapter import main
    main()
