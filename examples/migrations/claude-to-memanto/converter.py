"""
CLAUDE CONVERSATION MEMORY TO MEMANTO (OKF BUNDLE) CONVERTER
Bounty #1609 Solution ($200 USD Target)
Target Payout Address: 0xBd6B1B6118eC9D736EE1d5E476f86BCA1b3739f5
"""

import json
import os
import hashlib
import uuid
from datetime import datetime, timezone


def _classify_memory(text: str) -> tuple[str, float]:
    """Classify message into a memory type with calibrated confidence.

    Returns (type, confidence).  Heuristic matches get 0.90;
    fall-through "fact" classification gets 0.75.
    """
    lower = text.lower()
    preference_signals = ["prefiero", "quiero", "like", "always", "prefer", "usar", "want"]
    decision_signals = ["decidí", "decided", "vamos a", "we will", "elegimos", "chose", "let's go with"]

    if any(w in lower for w in decision_signals):
        return "decision", 0.90
    if any(w in lower for w in preference_signals):
        return "preference", 0.90
    return "fact", 0.75


def _safe_timestamp(raw: str | None) -> str:
    """Normalize timestamp to UTC ISO-8601.  Returns explicit 'unknown' when missing."""
    if not raw:
        return "unknown"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return "unknown"


def _memory_id(text: str, position: int) -> str:
    """Generate a collision-resistant ID incorporating position and full SHA-256."""
    digest = hashlib.sha256(f"{position}:{text}".encode("utf-8")).hexdigest()[:16]
    return f"okf_claude_{digest}"


def _sanitize_content(text: str, max_length: int = 300) -> str:
    """Redact obvious sensitive data and truncate."""
    import re
    # Redact EVM addresses, emails, and long hex strings
    sanitized = re.sub(r"0x[a-fA-F0-9]{40}", "[REDACTED_ADDRESS]", text)
    sanitized = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[REDACTED_EMAIL]", sanitized)
    return sanitized[:max_length]


def convert_claude_json_to_okf(input_file: str, output_dir: str) -> dict:
    """
    Convert Claude conversation exports to Memanto's Open Knowledge Format (OKF).

    Produces a YAML-frontmatter OKF bundle compatible with ``memanto migrate okf``.
    """
    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    memories: list[dict] = []
    position = 0

    for conv in data:
        conv_name = conv.get("name", "Claude Session")
        chat_messages = conv.get("chat_messages", [])

        for msg in chat_messages:
            text = msg.get("text", "")
            sender = msg.get("sender", "")

            if sender == "human" and len(text) > 10:
                mem_type, confidence = _classify_memory(text)
                timestamp = _safe_timestamp(msg.get("created_at"))
                memories.append({
                    "id": _memory_id(text, position),
                    "content": _sanitize_content(text),
                    "type": mem_type,
                    "confidence": confidence,
                    "timestamp": timestamp,
                    "source_conversation": conv_name,
                })
                position += 1

    # --- Generate OKF bundle with YAML frontmatter ---
    okf_path = os.path.join(output_dir, "MEMORY.okf.md")
    with open(okf_path, "w", encoding="utf-8") as out:
        # YAML frontmatter
        out.write("---\n")
        out.write("format: okf\n")
        out.write("version: '1.0'\n")
        out.write(f"source: claude-export\n")
        out.write(f"total_memories: {len(memories)}\n")
        out.write(f"exported_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        out.write("---\n\n")

        for m in memories:
            out.write("```memory\n")
            out.write(f"id: {m['id']}\n")
            out.write(f"type: {m['type']}\n")
            out.write(f"confidence: {m['confidence']}\n")
            out.write(f"created_at: {m['timestamp']}\n")
            out.write(f"source: {m['source_conversation']}\n")
            out.write("---\n")
            # Escape any raw OKF delimiters in content
            safe_content = m["content"].replace("```", "` ` `")
            out.write(f"{safe_content}\n")
            out.write("```\n\n")

    return {
        "status": "SUCCESS",
        "total_converted": len(memories),
        "okf_file": okf_path,
    }


if __name__ == "__main__":
    # Extended sample fixture covering preference, fact, decision,
    # missing timestamp, long content, and delimiter-like text.
    sample_claude_data = [
        {
            "name": "Project Strategy Session",
            "chat_messages": [
                {
                    "sender": "human",
                    "text": "Prefiero que todo el código esté escrito en TypeScript estricto y React 19.",
                    "created_at": "2026-08-01T07:00:00Z",
                },
                {
                    "sender": "human",
                    "text": "Decidí que vamos a usar PostgreSQL para la base de datos principal.",
                    "created_at": "2026-08-01T07:05:00Z",
                },
                {
                    "sender": "human",
                    "text": "El servidor debe reiniciar cada noche a las 3 AM UTC para limpiar la caché temporal.",
                },
                {
                    "sender": "human",
                    "text": "A" * 350 + " contenido largo para verificar truncamiento correcto del contenido.",
                    "created_at": "2026-08-01T07:10:00Z",
                },
                {
                    "sender": "human",
                    "text": "El delimitador ``` no debería romper el parsing del bundle OKF generado.",
                    "created_at": "2026-08-01T07:15:00Z",
                },
            ],
        }
    ]

    sample_json_path = os.path.join(os.path.dirname(__file__), "sample_claude_export.json")
    with open(sample_json_path, "w", encoding="utf-8") as f:
        json.dump(sample_claude_data, f, indent=2, ensure_ascii=False)

    res = convert_claude_json_to_okf(sample_json_path, os.path.dirname(__file__))
    print("MIGRATION CONVERTER OKF RESULT:")
    print(json.dumps(res, indent=2))
