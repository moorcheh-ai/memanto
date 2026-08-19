"""Reusable providers for LLM calls and embeddings with automatic key rotation.

Each service supports multiple API keys via numbered env vars:
    GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... (or GEMINI_API_KEY for single)
    GROQ_API_KEY_1, GROQ_API_KEY_2, ... (or GROQ_API_KEY for single)

When a key gets rate-limited (429), the KeyRing switches to the next key.
Checkpointing ensures progress is saved if all keys exhaust their quotas.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Literal


class KeyRing:
    """Manages multiple API keys, rotating on rate limits.

    Keys are read from environment variables:
        {PREFIX}_1, {PREFIX}_2, ..., {PREFIX}_9
    Falls back to {PREFIX} (without number) for single-key setups.
    """

    def __init__(self, env_prefix: str, service_name: str):
        self.prefix = env_prefix
        self.service = service_name
        self.keys: list[str] = []
        self.exhausted: set[int] = set()
        self.idx = 0

        # Read numbered keys: KEY_1, KEY_2, ...
        for i in range(1, 10):
            k = os.environ.get(f"{env_prefix}_{i}")
            if k:
                self.keys.append(k)
        # Fall back to unnumbered KEY
        if not self.keys:
            k = os.environ.get(env_prefix, "")
            if k:
                self.keys.append(k)

    def is_available(self) -> bool:
        return len(self.keys) > len(self.exhausted)

    def count(self) -> int:
        return len(self.keys)

    def exhausted_count(self) -> int:
        return len(self.exhausted)

    def get(self) -> str:
        """Return the current key, or raise if all exhausted."""
        if not self.keys:
            raise ValueError(
                f"No {self.service} API keys found. "
                f"Set {self.prefix}_1 (or {self.prefix})."
            )
        if not self.is_available():
            raise RuntimeError(
                f"All {len(self.keys)} {self.service} API keys exhausted "
                f"(rate-limited). Add more via {self.prefix}_N or wait."
            )

        # Find the next non-exhausted key
        for _ in range(len(self.keys)):
            if self.idx not in self.exhausted:
                key = self.keys[self.idx]
                _masked = key[:8] + "..." + key[-4:]
                return key
            self.idx = (self.idx + 1) % len(self.keys)

        raise RuntimeError(f"All {self.service} API keys exhausted")

    def on_rate_limit(self) -> bool:
        """Mark current key as exhausted and advance to next.

        Returns True if another key is available, False if all exhausted.
        """
        self.exhausted.add(self.idx)
        self.idx = (self.idx + 1) % len(self.keys)
        remaining = len(self.keys) - len(self.exhausted)
        if remaining <= 0:
            print(
                f"    ⚠ All {self.service} API keys exhausted ({len(self.keys)} keys)"
            )
            return False
        print(
            f"    ⚠ {self.service} key exhausted, rotating to next ({remaining} left)"
        )
        return True


# Global key rings (lazy loaded)
_groq_keys: KeyRing | None = None
_gemini_keys: KeyRing | None = None


def _get_groq_keys() -> KeyRing:
    global _groq_keys
    if _groq_keys is None:
        _groq_keys = KeyRing("GROQ_API_KEY", "Groq")
    return _groq_keys


def _get_gemini_keys() -> KeyRing:
    global _gemini_keys
    if _gemini_keys is None:
        _gemini_keys = KeyRing("GEMINI_API_KEY", "Gemini")
    return _gemini_keys


# ---------------------------------------------------------------------------
# Groq — chat completions (LLM)
# ---------------------------------------------------------------------------

GROQ_DEFAULT_MODEL = "llama-3.1-8b-instant"


def groq_chat(
    messages: list[dict],
    model: str = GROQ_DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    api_key: str = "",
) -> str:
    """Call Groq's chat-completion API with automatic key rotation."""
    from groq import Groq

    key_ring = _get_groq_keys()

    for key_try in range(key_ring.count() or 1):
        key = api_key or key_ring.get()
        client = Groq(api_key=key)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            err = str(e)
            if "429" in err:
                print(f"    Groq rate-limited on key {key_try + 1}")
                if not api_key and not key_ring.on_rate_limit():
                    break
                time.sleep(5)
            else:
                raise

    raise RuntimeError("All Groq API keys exhausted")


def groq_judge(
    question: str,
    expected: str,
    retrieved_texts: list[str],
    model: str = GROQ_DEFAULT_MODEL,
    api_key: str = "",
) -> bool:
    """Ask Groq whether the expected answer appears in the retrieved chunks."""
    chunks = (
        "\n\n".join(
            f"[{i + 1}] {t[:600]}"
            for i, t in enumerate(retrieved_texts[:10])
            if t.strip()
        )
        or "(nothing retrieved)"
    )

    prompt = (
        f"Given this text from a knowledge base:\n\n{chunks}\n\n"
        f"Question: {question}\n"
        f"Expected answer: {expected}\n\n"
        f"Does the text contain the expected answer (verbatim or implied)? "
        f"Reply with exactly one word: YES or NO."
    )

    answer = groq_chat(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.0,
        max_tokens=5,
        api_key=api_key,
    )
    return "YES" in answer.upper()


# ---------------------------------------------------------------------------
# Gemini — embeddings
# ---------------------------------------------------------------------------

GEMINI_DEFAULT_EMBED_MODEL = "gemini-embedding-2"


def gemini_embed(
    text: str | list[str],
    model: str = GEMINI_DEFAULT_EMBED_MODEL,
    api_key: str = "",
    task_type: Literal[
        "RETRIEVAL_DOCUMENT",
        "RETRIEVAL_QUERY",
        "SEMANTIC_SIMILARITY",
        "CLASSIFICATION",
    ] = "RETRIEVAL_DOCUMENT",
) -> list[float] | list[list[float]]:
    """Embed one or more strings via Gemini with automatic key rotation."""
    key_ring = _get_gemini_keys()
    single = isinstance(text, str)
    texts = [text] if single else text

    for key_try in range(key_ring.count() or 1):
        key = api_key or key_ring.get()

        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{model}:batchEmbedContents?key={key}"
        )
        body = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                }
                for t in texts
            ]
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            embeddings = [e["values"] for e in data.get("embeddings", [])]
            return embeddings[0] if single else embeddings

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"    Gemini rate-limited on key {key_try + 1}")
                if not api_key and not key_ring.on_rate_limit():
                    break
                time.sleep(5)
            else:
                raise

    raise RuntimeError("All Gemini API keys exhausted")


# ---------------------------------------------------------------------------
# Cluster — user's private ML endpoint (no rate limits)
# ---------------------------------------------------------------------------
# Local embedding — calls the local API server (localhost:8080)
# ---------------------------------------------------------------------------

LOCAL_BASE = "http://127.0.0.1:8080/v1"


def local_embed(
    text: str | list[str],
) -> list[float] | list[list[float]]:
    """Embed text via the local API server's all-MiniLM-L6-v2 endpoint."""
    import requests as _req

    single = isinstance(text, str)
    payload = {"input": [text] if single else text}

    resp = _req.post(
        f"{LOCAL_BASE}/embeddings",
        headers={"Content-Type": "application/json", "User-Agent": "MemantoBench/1.0"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    embeddings = [
        e["embedding"] for e in sorted(data.get("data", []), key=lambda x: x["index"])
    ]
    return embeddings[0] if single else embeddings


# ---------------------------------------------------------------------------
# Cluster (legacy — not used, replaced by local API server)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Environment help
# ---------------------------------------------------------------------------

REQUIRED_KEYS: dict[str, str] = {
    "GROQ_API_KEY": "Groq LLM — set GROQ_API_KEY_1..N for multiple keys",
    "GEMINI_API_KEY": "Gemini embedding — set GEMINI_API_KEY_1..N for multiple keys",
    "MOORCHEH_API_KEY": "Memanto/Moorcheh — get at https://moorcheh.ai",
    "ZEP_API_KEY": "Zep Cloud — get at https://getzep.com",
    "SUPERMEMORY_API_KEY": "Supermemory — get at https://supermemory.ai",
}


def check_keys(*names: str) -> bool:
    """Check that at least one key is available for each named service."""
    ok = True
    for name in names:
        kr = None
        if name.startswith("GROQ"):
            kr = _get_groq_keys()
        elif name.startswith("GEMINI"):
            kr = _get_gemini_keys()
        else:
            if not os.environ.get(name):
                print(f"    ✗  {name} not set  ({REQUIRED_KEYS.get(name, '')})")
                ok = False
            continue

        if kr and kr.count() == 0:
            print(f"    ✗  {name} not set  ({REQUIRED_KEYS.get(name, '')})")
            ok = False
        elif kr:
            print(f"    ✓  {name} ({kr.count()} key(s) loaded)")
    return ok
