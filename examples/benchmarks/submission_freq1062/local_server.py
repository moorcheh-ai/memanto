"""Local OpenAI-compatible API server for LLM + embeddings.

Listens on 127.0.0.1:8080, providing:
  GET  /health               → {"status":"ok"}
  POST /v1/chat/completions  → llama-cpp chat
  POST /v1/embeddings        → sentence-transformers embed

Start with:
  BENCH_MODEL_PATH=/path/to/model.gguf python3 local_server.py
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

_llm = None
_embed_model = None

MODEL_PATH = os.environ.get(
    "BENCH_MODEL_PATH",
    os.path.expanduser("~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
)


def _get_llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama

        _llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=16384,
            n_gpu_layers=33,
            verbose=False,
        )
    return _llm


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer

        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def local_chat(
    messages: list[dict], temperature: float = 0.0, max_tokens: int = 2048
) -> str:
    """Chat via llama-cpp-python's built-in chat handler (uses model's native template)."""
    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (response["choices"][0]["message"]["content"] or "").strip()


def local_embed(text: str | list[str]) -> list[float] | list[list[float]]:
    model = _get_embed_model()
    single = isinstance(text, str)
    texts = [text] if single else text
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()
    return embeddings[0] if single else embeddings


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class OpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence logs

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/v1/chat/completions":
            messages = body.get("messages", [])
            temperature = body.get("temperature", 0.0)
            max_tokens = body.get("max_tokens", 2048)

            try:
                response = local_chat(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
                self._send_json(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": response}}
                        ],
                        "usage": {"total_tokens": len(response.split())},
                    }
                )
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/v1/embeddings":
            inp = body.get("input", "")
            try:
                embeddings = local_embed(inp)
                if isinstance(inp, str):
                    embeddings = [embeddings]
                data = [{"embedding": e, "index": i} for i, e in enumerate(embeddings)]
                self._send_json(
                    {
                        "object": "list",
                        "data": data,
                        "model": "all-MiniLM-L6-v2",
                    }
                )
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        else:
            self._send_json({"error": "not found"}, 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("BENCH_PORT", 8080))
    server = HTTPServer(("127.0.0.1", port), OpenAIHandler)
    print(f"Local API server on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
