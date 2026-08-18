"""
Agent Service for MEMANTO

Handles agent creation, listing, and lifecycle management.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout
from moorcheh_sdk.exceptions import ConflictError
from pydantic import ValidationError

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.config import get_data_dir
from memanto.app.core import agent_namespace
from memanto.app.models.session import AgentCreate, AgentInfo, AgentList
from memanto.app.utils.atomic_write import atomic_write_text
from memanto.app.utils.errors import AgentAlreadyExistsError, AgentNotFoundError, NamespaceError
from memanto.app.utils.temporal_helpers import as_utc_aware
from memanto.app.utils.validation import validate_safe_id

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agents"""

    def __init__(self, agents_dir: Path | None = None):
        """
        Initialize agent service

        Args:
            agents_dir: Directory for agent metadata storage (defaults to ~/.memanto/agents/)
        """
        self.agents_dir = agents_dir or get_data_dir() / "agents"

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
        """
        agent_file = self._get_agent_file(agent_create.agent_id)
        if agent_file.exists():
            raise AgentAlreadyExistsError(
                f"Agent '{agent_create.agent_id}' already exists"
            )

        self.agents_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(agent_file) + ".lock")

        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise AgentAlreadyExistsError(
                f"Agent '{agent_create.agent_id}' already exists"
            ) from exc

        try:
            # Re-check after taking the inter-process lock. Another creator may
            # have completed between the optimistic check above and acquisition.
            if agent_file.exists():
                raise AgentAlreadyExistsError(
                    f"Agent '{agent_create.agent_id}' already exists"
                )

            namespace = self._generate_namespace(agent_create.agent_id)
            client = get_moorcheh_client(api_key=moorcheh_api_key)

            try:
                client.namespaces.create(namespace, type="text")
                print(f"[OK] Namespace created in Moorcheh: {namespace}")
            except Exception as exc:
                message = str(exc).lower()
                if "limit" in message or "tier" in message or "quota" in message:
                    raise NamespaceError(f"Moorcheh namespace limit reached: {exc}")
                if isinstance(exc, ConflictError) or (
                    "namespace" in message and "already exists" in message
                ) or "conflict" in message:
                    print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
                else:
                    raise Exception(
                        f"Failed to create namespace '{namespace}' in Moorcheh: {exc}"
                    )

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
            self._save_agent(agent)
            return agent
        finally:
            # FileLock uses an OS-backed lock. The marker file may remain, but
            # the lock itself is released automatically even if the process dies.
            lock.release()

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """
        Get agent by ID

        Args:
            agent_id: Agent identifier

        Returns:
            AgentInfo or None if not found
        """
        agent_file = self._get_agent_file(agent_id)
        if not agent_file.exists():
            return None

        try:
            return self._load_agent_file(agent_file)
        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValidationError,
            UnicodeDecodeError,
        ) as exc:
            logger.warning("Skipping invalid agent file %s: %s", agent_file, exc)
            return None

    def list_agents(self) -> AgentList:
        """
        List all agents

        Returns:
            AgentList with all agents
        """
        agents: list[AgentInfo] = []
        warnings: list[str] = []
        if not self.agents_dir.exists():
            return AgentList(agents=agents, count=0, warnings=warnings)

        for agent_file in self.agents_dir.glob("*.json"):
            try:
                agent = self._load_agent_file(agent_file)
                if agent is not None:
                    agents.append(agent)
            except (
                OSError,
                json.JSONDecodeError,
                TypeError,
                ValidationError,
                UnicodeDecodeError,
            ) as exc:
                logger.warning("Skipping invalid agent file %s: %s", agent_file, exc)
                warnings.append(f"Could not load agent file '{agent_file.name}': {exc}")

        # Sort by created_at (newest first); normalize for legacy naive timestamps.
        agents.sort(key=lambda a: as_utc_aware(a.created_at), reverse=True)

        return AgentList(agents=agents, count=len(agents), warnings=warnings)

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
            AgentNotFoundError: If agent doesn't exist
        """
        agent_file = self._get_agent_file(agent_id)
        lock_file = agent_file.with_suffix(".json.lock")

        with FileLock(str(lock_file), timeout=5):
            if not agent_file.exists():
                raise AgentNotFoundError(f"Agent '{agent_id}' not found")

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

    def _save_agent(self, agent: AgentInfo) -> None:
        """Save agent metadata to file"""
        agent_file = self._get_agent_file(agent.agent_id)
        atomic_write_text(
            agent_file,
            json.dumps(agent.model_dump(mode="json"), indent=2),
        )

    def _load_agent_file(self, agent_file: Path) -> AgentInfo | None:
        """Load one agent metadata file. Raises exception if file is corrupted."""
        if not agent_file.exists():
            return None

        with open(agent_file) as f:
            data = json.load(f)
        return AgentInfo(**data)
