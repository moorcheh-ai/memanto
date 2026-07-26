"""
Agent Service for MEMANTO

Handles agent creation, listing, and lifecycle management.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import Mock

from moorcheh_sdk.exceptions import ConflictError, MoorchehError

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.config import get_data_dir
from memanto.app.core import agent_namespace
from memanto.app.models.session import AgentCreate, AgentInfo, AgentList
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentLimitExceededError,
    AgentNotFoundError,
    NamespaceError,
)
from memanto.app.utils.temporal_helpers import as_utc_aware
from memanto.app.utils.validation import validate_safe_id

# Transport-level timeout for Moorcheh namespace creation so a hung HTTP call
# is cancelled by the client (not a ThreadPoolExecutor watchdog).
_NAMESPACE_CREATE_TIMEOUT_SEC = float(
    os.environ.get("MEMANTO_NAMESPACE_CREATE_TIMEOUT_SEC", "15")
)


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    """Cross-platform exclusive lock (fcntl on Unix, msvcrt on Windows)."""
    lock_path.touch(exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class AgentService:
    """Service for managing agents"""

    def __init__(self, agents_dir: Path | None = None):
        """
        Initialize agent service

        Args:
            agents_dir: Directory for agent metadata storage (defaults to ~/.memanto/agents/)
        """
        self.agents_dir = agents_dir or get_data_dir() / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

    def _generate_namespace(self, agent_id: str) -> str:
        """
        Generate the Moorcheh namespace for an agent.

        Format: memanto_agent_{agent_id}
        """
        return agent_namespace(agent_id)

    def _get_agent_file(self, agent_id: str) -> Path:
        """Get file path for agent metadata"""
        validate_safe_id(agent_id, "agent_id")
        return self.agents_dir / f"{agent_id}.json"

    def _load_agent_file(self, agent_file: Path) -> AgentInfo | None:
        """Load agent metadata; skip empty/incomplete placeholders."""
        try:
            if agent_file.stat().st_size == 0:
                return None
            with open(agent_file) as f:
                data = json.load(f)
            return AgentInfo(**data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _get_namespace_create_client(self, moorcheh_api_key: str) -> Any:
        """Client whose HTTP timeout matches the namespace-create budget.

        Uses a dedicated transport timeout so hung ``namespaces.create`` calls
        are cancelled at the HTTP layer. Test doubles injected via
        ``get_moorcheh_client()`` are returned unchanged.
        """
        timeout = _NAMESPACE_CREATE_TIMEOUT_SEC
        base = get_moorcheh_client()
        if isinstance(base, Mock):
            return base

        from memanto.app.clients.backend import Backend, parse_backend
        from memanto.app.config import settings

        if parse_backend(settings.MEMANTO_BACKEND) == Backend.ON_PREM:
            from memanto.app.clients.onprem import OnPremClient

            return OnPremClient(
                base_url=settings.MOORCHEH_ONPREM_URL,
                timeout=max(1, int(round(timeout))),
            )

        from moorcheh_sdk import MoorchehClient

        key = (
            moorcheh_api_key
            or getattr(base, "api_key", None)
            or settings.MOORCHEH_API_KEY
        )
        return MoorchehClient(api_key=key, timeout=timeout)

    def create_agent(
        self, agent_create: AgentCreate, moorcheh_api_key: str
    ) -> AgentInfo:
        """
        Create a new agent

        Args:
            agent_create: Agent creation request
            moorcheh_api_key: Moorcheh API key for namespace creation

        Returns:
            AgentInfo object

        Raises:
            AgentAlreadyExistsError: If agent already exists
            AgentLimitExceededError: If account agent limit is reached
        """
        agent_file = self._get_agent_file(agent_create.agent_id)

        # Cross-process capacity lock: serialize claim + plan-limit check so
        # concurrent creators with distinct IDs cannot all pass the limit.
        with _exclusive_file_lock(self.agents_dir / ".capacity.lock"):
            # Atomic creation: exclusive open prevents TOCTOU duplicate-ID races.
            try:
                fd = open(agent_file, "x")
                fd.close()
            except FileExistsError:
                raise AgentAlreadyExistsError(
                    f"Agent '{agent_create.agent_id}' already exists"
                )

            # Check agent count limit AFTER claiming the slot.
            # Community plan: max 2 agents. Remove the file if over limit.
            current_count = len(list(self.agents_dir.glob("*.json")))
            max_agents = self._get_max_agents()
            if current_count > max_agents:
                agent_file.unlink(missing_ok=True)
                raise AgentLimitExceededError(
                    f"Agent limit reached ({max_agents}). "
                    f"Upgrade your plan to create more agents."
                )

        namespace = self._generate_namespace(agent_create.agent_id)

        # Wrap all post-claim work in try/except to release the placeholder
        # if namespace creation or metadata save fails.
        try:
            # Create namespace in Moorcheh - CRITICAL: Must succeed.
            # Transport timeout cancels hung HTTP so plan quota is released promptly.
            client = self._get_namespace_create_client(moorcheh_api_key)

            try:
                client.namespaces.create(namespace, type="text")
                print(f"[OK] Namespace created in Moorcheh: {namespace}")
            except ConflictError:
                # Namespace already exists - this is OK, agent might have been created before
                print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
            except MoorchehError as e:
                msg = str(e).lower()
                if "timed out" in msg or "timeout" in msg:
                    raise NamespaceError(
                        f"Timed out creating namespace '{namespace}' in Moorcheh "
                        f"after {_NAMESPACE_CREATE_TIMEOUT_SEC:g}s"
                    ) from e
                if ("namespace" in msg and "already exists" in msg) or "conflict" in msg:
                    print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
                else:
                    raise NamespaceError(
                        f"Failed to create namespace '{namespace}' in Moorcheh: {str(e)}"
                    ) from e
            except Exception as e:
                # On-prem raises moorcheh.errors.MoorchehApiError (HTTP 409) rather
                # than the cloud SDK's typed ConflictError when the namespace
                # already exists. Match on message so both backends behave the same.
                msg = str(e).lower()
                if "timed out" in msg or "timeout" in msg:
                    raise NamespaceError(
                        f"Timed out creating namespace '{namespace}' in Moorcheh "
                        f"after {_NAMESPACE_CREATE_TIMEOUT_SEC:g}s"
                    ) from e
                if ("namespace" in msg and "already exists" in msg) or "conflict" in msg:
                    print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
                else:
                    raise NamespaceError(
                        f"Failed to create namespace '{namespace}' in Moorcheh: {str(e)}"
                    ) from e

            # Create agent metadata
            agent = AgentInfo(
                agent_id=agent_create.agent_id,
                namespace=namespace,
                pattern=agent_create.pattern,
                description=agent_create.description,
                created_at=datetime.now(timezone.utc),
                memory_count=0,
                session_count=0,
                status="ready",
            )

            # Save agent metadata — also covered by cleanup on failure
            self._save_agent(agent)
        except Exception:
            # Release the claimed file slot on any failure
            agent_file.unlink(missing_ok=True)
            raise

        return agent

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """
        Get agent by ID

        Args:
            agent_id: Agent identifier

        Returns:
            AgentInfo or None if not found / incomplete placeholder
        """
        agent_file = self._get_agent_file(agent_id)
        if not agent_file.exists():
            return None
        return self._load_agent_file(agent_file)

    def list_agents(self) -> AgentList:
        """
        List all agents

        Returns:
            AgentList with all agents
        """
        agents = []
        for agent_file in self.agents_dir.glob("*.json"):
            agent = self._load_agent_file(agent_file)
            if agent is not None:
                agents.append(agent)

        # Sort by created_at (newest first); normalize for legacy naive timestamps.
        agents.sort(key=lambda a: as_utc_aware(a.created_at), reverse=True)

        return AgentList(agents=agents, count=len(agents))

    def update_agent_stats(
        self,
        agent_id: str,
        last_session: datetime | None = None,
        increment_session_count: bool = False,
    ) -> AgentInfo:
        """
        Update agent statistics

        Args:
            agent_id: Agent identifier
            last_session: Last session timestamp
            increment_session_count: Whether to increment session count

        Returns:
            Updated AgentInfo

        Raises:
            AgentNotFoundError: If agent doesn't exist
        """
        agent = self.get_agent(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        if last_session:
            agent.last_session = last_session

        if increment_session_count:
            agent.session_count += 1

        self._save_agent(agent)
        return agent

    def delete_agent(self, agent_id: str) -> None:
        """
        Delete agent

        Args:
            agent_id: Agent identifier

        Raises:
            AgentNotFoundError: If agent doesn't exist or is an in-progress
                capacity placeholder (non-loadable claim file)
        """
        agent_file = self._get_agent_file(agent_id)
        # Serialize with create_agent capacity claims so delete cannot unlink a
        # placeholder mid-create and free the plan slot for a second creator.
        with _exclusive_file_lock(self.agents_dir / ".capacity.lock"):
            if not agent_file.exists():
                raise AgentNotFoundError(f"Agent '{agent_id}' not found")

            agent = self._load_agent_file(agent_file)
            if agent is None:
                raise AgentNotFoundError(
                    f"Agent '{agent_id}' is not ready (creation in progress)"
                )

            agent_file.unlink()

    def agent_exists(self, agent_id: str) -> bool:
        """
        Check if agent exists

        Args:
            agent_id: Agent identifier

        Returns:
            True if agent exists
        """
        return self._get_agent_file(agent_id).exists()

    def _get_max_agents(self) -> int:
        """Get maximum allowed agents for current plan.

        Checks MEMANTO_MAX_AGENTS env var, defaults to community plan (2).
        """
        try:
            return int(os.environ.get("MEMANTO_MAX_AGENTS", "2"))
        except (TypeError, ValueError):
            return 2

    def _save_agent(self, agent: AgentInfo) -> None:
        """Save agent metadata to file"""
        agent_file = self._get_agent_file(agent.agent_id)
        with open(agent_file, "w") as f:
            json.dump(agent.model_dump(mode="json"), f, indent=2)
