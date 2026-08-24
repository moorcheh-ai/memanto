"""
Shared ZIP loading helper for conversation migration scripts.
Mirrors the extraction logic in migrate.py and app.py.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def load_conversation_zip(zip_path: Path, provider: str) -> dict[str, Any] | None:
    try:
        file_bytes = zip_path.read_bytes()
    except OSError as exc:
        print(f"Cannot read {zip_path}: {exc}", file=sys.stderr)
        return None

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for member in zf.infolist():
                    dest = (tmp_path / member.filename).resolve()
                    if not dest.is_relative_to(tmp_path):
                        print("ZIP archive contains unsafe paths.", file=sys.stderr)
                        return None
                zf.extractall(tmp)
        except zipfile.BadZipFile as exc:
            print(f"Invalid ZIP: {exc}", file=sys.stderr)
            return None

        if provider == "gemini":
            return _parse_gemini(tmp_path)

        json_file = tmp_path / "conversations.json"
        if not json_file.exists():
            candidates = list(tmp_path.rglob("conversations.json"))
            if not candidates:
                print("conversations.json not found in ZIP.", file=sys.stderr)
                return None
            json_file = candidates[0]

        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"conversations.json is not valid JSON: {exc}", file=sys.stderr)
            return None

        return {"memories": raw} if isinstance(raw, list) else raw


def _parse_gemini(tmp_path: Path) -> dict[str, Any]:
    json_hits = list(tmp_path.rglob("My Activity.json"))
    if json_hits:
        entries = json.loads(json_hits[0].read_text(encoding="utf-8"))
        memories = []
        for entry in entries or []:
            title = (entry.get("title") or "").strip()
            prompt = re.sub(r"^Prompted\s+", "", title).strip()
            if prompt:
                memories.append({
                    "messages": [{"role": "user", "text": prompt}],
                    "createdTime": entry.get("time"),
                    "id": entry.get("gmr_id"),
                })
        return {"memories": memories}

    html_hits = list(tmp_path.rglob("My Activity.html"))
    if html_hits:
        raw = html_hits[0].read_text(encoding="utf-8", errors="replace")
        entries = re.findall(r'Prompted\s+(.*?)(?=Prompted\s|$)', raw, re.DOTALL)
        memories = []
        for e in entries:
            text = re.sub(r'<[^>]+>', '', e).strip()
            if text:
                memories.append({"messages": [{"role": "user", "text": text[:500]}]})
        return {"memories": memories}

    return {"memories": []}
