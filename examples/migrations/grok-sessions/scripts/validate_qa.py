"""Golden Q&A against the generated OKF bundle (no LLM).

Each question is answered by looking up typed documents in sample-okf, which is
the same recall check a reviewer can do by reading the markdown wiki.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "sample-okf"


def blob() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in BUNDLE.rglob("*.md"))


def typed(kind: str) -> str:
    folder = BUNDLE / "memories" / kind
    if not folder.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8") for p in folder.glob("*.md") if p.name != "index.md")


def main() -> int:
    text = blob()
    questions = [
        ("What language should reports use?", "PT-BR" in typed("preference")),
        ("Which local project may be changed?", "grokgrana" in typed("fact")),
        ("Which sibling project must stay untouched?", "Não mexer" in typed("fact") or "nao mexer" in typed("fact").lower()),
        ("What snapshot rule did the operator give?", "take_snapshot" in typed("observation")),
        ("Was the hunter email redacted?", "hunter@example.com" not in text and "[REDACTED]" in text),
        ("Is the bundle OKF v0.2?", 'okf_version: "0.2"' in text),
        ("Are live filesystem paths omitted from the episode?", "C:/Users" not in text and "C:\\Users" not in text),
    ]
    failed = [name for name, ok in questions if not ok]
    for name, ok in questions:
        print(("PASS" if ok else "FAIL"), name)
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    print("all golden questions matched the OKF bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
