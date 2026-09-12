"""Golden Q&A against the generated OKF bundle (no LLM)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "sample-okf"


def blob() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in BUNDLE.rglob("*.md"))


def main() -> int:
    text = blob()
    checks = [
        ("report language", "PT-BR" in text),
        ("grokgrana map", "grokgrana" in text),
        ("grana untouched", "Não mexer" in text or "nao mexer" in text.lower()),
        ("snapshot rule", "take_snapshot" in text),
        ("email redacted", "hunter@example.com" not in text and "[REDACTED]" in text),
        ("okf version", 'okf_version: "0.2"' in text),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL"), name)
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    print("all golden questions matched the OKF bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
