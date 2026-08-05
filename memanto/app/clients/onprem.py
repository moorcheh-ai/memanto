"""
On-prem Moorcheh client.

Wraps ``moorcheh.MoorchehClient`` (``moorcheh-client>=0.1.3``) and exposes the
same ``namespaces / documents / similarity_search / answer / files / vectors``
shape that the cloud SDK does, so Memanto's service layer never branches on
backend. Only one thin adapter is needed: ``_DocumentsAdapter`` adds cloud's
``documents.upload_file(namespace, path)`` on top of on-prem's
``files.upload(namespace, files=[{path: container_path}])`` (copies into
``~/.moorcheh/uploads`` and converts the host path).

The ``ai_model`` value passed to ``answer.generate`` is the caller's
responsibility — on-prem callers must source it from
``~/.memanto/on-prem/state.json`` via ``config_manager.get_answer_config()``,
which is backend-aware. No silent model coercion happens here.
"""

from pathlib import Path
from typing import Any

_DEFAULT_URL = "http://localhost:8080"


def _import_raw_client() -> Any:
    """Lazy import so the cloud path doesn't require ``moorcheh-client``."""
    try:
        from moorcheh import MoorchehClient  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - exercised at runtime only
        raise RuntimeError(
            "moorcheh-client is not installed. Run: pip install moorcheh-client"
        ) from e
    return MoorchehClient


def _import_docker_runtime_helpers() -> tuple[Any, Any]:
    """Lazy import of upload-dir helpers; only needed for ``upload_file``."""
    try:
        from moorcheh.docker_runtime import (  # type: ignore[import-not-found]
            ensure_upload_dir,
            host_path_to_container_upload_path,
        )
    except ImportError as e:  # pragma: no cover - exercised at runtime only
        raise RuntimeError(
            "moorcheh.docker_runtime helpers are unavailable. "
            "Upgrade with: pip install -U moorcheh-client"
        ) from e
    return ensure_upload_dir, host_path_to_container_upload_path


class _DocumentsAdapter:
    """Wraps ``client.documents`` to add ``upload_file`` (cloud-shape) on top of
    on-prem's ``client.files.upload``.

    All other methods (upload, get, delete, fetch_text_data) pass through to
    the native on-prem ``documents`` resource unchanged.
    """

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def __getattr__(self, name: str) -> Any:
        # Delegate any method not defined here (upload, get, delete,
        # fetch_text_data, upload_job_status) to the real on-prem documents
        # resource. Only invoked for attrs not found on the instance.
        return getattr(self._raw.documents, name)

    def upload_file(self, namespace_name: str, file_path: str | Path) -> dict:
        """Cloud-shape ``documents.upload_file`` for on-prem.

        Copies the file into ``~/.moorcheh/uploads``, converts the host path
        to the container-visible path, and submits via ``client.files.upload``.

        Returns a dict shaped like the cloud SDK's ``FileUploadResponse``
        (``success``, ``message``, ``file_name``, ``file_size``,
        ``namespace``) so route handlers don't need to branch by backend.
        Note: on-prem upload is asynchronous; ``success=True`` here means the
        job was accepted, not that indexing has completed.
        """
        import shutil
        import uuid

        ensure_upload_dir, host_path_to_container_upload_path = (
            _import_docker_runtime_helpers()
        )

        src = Path(file_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"upload_file: not a file: {src}")

        upload_root = ensure_upload_dir()
        staged_name = f"{src.stem}-{uuid.uuid4().hex}{src.suffix}"
        host_file = (upload_root / staged_name).resolve()
        shutil.copy2(src, host_file)
        container_path = host_path_to_container_upload_path(host_file, upload_root)

        resp = self._raw.files.upload(
            namespace_name,
            files=[{"path": container_path, "force_reindex": False}],
        )
        if not isinstance(resp, dict):
            resp = {}
        return {
            "success": True,
            "message": resp.get("message", "Upload job submitted."),
            "namespace": namespace_name,
            "file_name": src.name,
            "file_size": host_file.stat().st_size if host_file.exists() else None,
            "job_id": resp.get("job_id"),
        }


class OnPremClient:
    """Cloud-shaped facade over ``moorcheh.MoorchehClient``."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        client_cls = _import_raw_client()
        # ``moorcheh.MoorchehClient`` defaults timeout=30 which is too short
        # for first-call LLM cold-starts (Ollama can take 1-2 minutes to load
        # qwen2.5). Honor the caller's timeout when provided; otherwise let
        # the raw client use its own default.
        if timeout is not None:
            self._raw = client_cls(base_url or _DEFAULT_URL, timeout=timeout)
        else:
            self._raw = client_cls(base_url or _DEFAULT_URL)
        # Native resources expose the same shape as the cloud SDK — pass through.
        self.namespaces = self._raw.namespaces
        self.similarity_search = self._raw.similarity_search
        self.answer = self._raw.answer
        self.vectors = self._raw.vectors
        self.files = self._raw.files
        # Only ``documents`` needs an adapter (cloud's ``upload_file`` shim).
        self.documents = _DocumentsAdapter(self._raw)

    def health(self) -> Any:
        return self._raw.health()


class AsyncOnPremClient(OnPremClient):
    """Async facade. Memanto only awaits a handful of methods via
    ``asyncio.to_thread`` today, so we expose the same sync ``OnPremClient``
    shape — existing ``await asyncio.to_thread(client.documents.upload, ...)``
    calls keep working unchanged.
    """
