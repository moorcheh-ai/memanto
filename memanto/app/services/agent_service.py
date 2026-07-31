"""
Agent Service for MEMANTO

Handles agent creation, listing, and lifecycle management.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from moorcheh_sdk.exceptions import ConflictError
from pydantic import ValidationError

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.config import get_data_dir
from memanto.app.core import agent_namespace
from memanto.app.models.session import AgentCreate, AgentInfo, AgentList
from memanto.app.utils.atomic_write import atomic_write_text
from memanto.app.utils.errors import AgentAlreadyExistsError, AgentNotFoundError
from memanto.app.utils.temporal_helpers import as_utc_aware
from memanto.app.utils.validation import validate_safe_id

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agents"""

    def __init__(self, agents_dir: Path | None = None):
        self.agents_dir = agents_dir or get_data_dir() / "agents"

    def _generate_namespace(self, agent_id: str) -> str:
        return agent_namespace(agent_id)

    def _get_agent_file(self, agent_id: str) -> Path:
        validate_safe_id(agent_id, "agent_id")
        return self.agents_dir / f"{agent_id}.json"

    def create_agent(
        self, agent_create: AgentCreate, moorcheh_api_key: str
    ) -> AgentInfo:
        agent_file = self._get_agent_file(agent_create.agent_id)
        if agent_file.exists():
            raise AgentAlreadyExistsError(
                f"Agent '{agent_create.agent_id}' already exists"
            )

        lock_file = agent_file.with_suffix(".json.lock")
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(lock_file, "x"):
                pass
        except FileExistsError:
            raise AgentAlreadyExistsError(
                f"Agent '{agent_create.agent_id}' already exists"
            )

        try:
            namespace = self._generate_namespace(agent_create.agent_id)
            client = get_moorcheh_client(api_key=moorcheh_api_key)

            try:
                client.namespaces.create(namespace, type="text")
                print(f"[OK] Namespace created in Moorcheh: {namespace}")
            except ConflictError:
                print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
            except Exception as exc:
                message = str(exc).lower()
                if (
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
            lock_file.unlink(missing_ok=True)

    def get_agent(self, agent_id: str) -> AgentInfo | None:
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

        agents.sort(key=lambda a: as_utc_aware(a.created_at), reverse=True)
        return AgentList(agents=agents, count=len(agents), warnings=warnings)

    def update_agent_stats(
        self,
        agent_id: str,
        last_session: datetime | None = None,
        increment_session_count: bool = False,
    ) -> AgentInfo:
        agent = self.get_agent(agent_id)
        if not agent:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        if last_session:
            agent.last_session = last_session

        if increment_session_count:
            agent.session_count += 1

        self._save_agent(agent)
        return agent

    def delete_agent(self, agent_id: str, moorcheh_api_key: str | None = None) -> None:
        """
        Delete agent and clean up ALL associated resources.

        Previously this only removed the local .json metadata file, leaving:
        - Moorcheh namespace (memanto_agent_{id}) with all stored memories
        - Session files in ~/.memanto/sessions/{agent_id}_*.json
        - Conflict reports in ~/.memanto/conflicts/{agent_id}_*
        - Stale .json.lock files blocking re-creation

        When a new agent was created with the same ID, the namespace conflict
        was silently ignored and the new agent would see the deleted agent's
        memories via search queries -- a data resurrection / isolation bug.

        Args:
            agent_id: Agent identifier
            moorcheh_api_key: Optional API key for namespace deletion on server

        Raises:
            AgentNotFoundError: If agent doesn't exist
        """
        agent_file = self._get_agent_file(agent_id)
        if not agent_file.exists():
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

        # Remove the agent metadata file
        agent_file.unlink()

        # Remove any stale lock file left by a crashed create_agent
        lock_file = agent_file.with_suffix(".json.lock")
        lock_file.unlink(missing_ok=True)

        # Best-effort deletion of the Moorcheh namespace on the server.
        # This prevents data resurrection: without it, a new agent created
        # with the same ID would inherit the deleted agent's memories.
        if moorcheh_api_key:
            try:
                namespace = self._generate_namespace(agent_id)
                client = get_moorcheh_client(api_key=moorcheh_api_key)
                client.namespaces.delete(namespace)
                logger.info("Deleted Moorcheh namespace '%s' for agent '%s'", namespace, agent_id)
            except Exception as exc:
                logger.warning(
                    "Could not delete Moorcheh namespace '%s' for agent '%s': %s. "
                    "Memories may persist on the server and resurface if an agent "
                    "with the same ID is created later.",
                    namespace, agent_id, exc,
                )

        # Clean up orphaned session files for this agent
        sessions_dir = self.agents_dir.parent / "sessions"
        if sessions_dir.exists():
            for session_file in sessions_dir.glob(f"{agent_id}_*.json"):
                try:
                    session_file.unlink()
                    logger.debug("Removed orphaned session file %s", session_file)
                except OSError:
                    pass
            # Remove active session symlink if it points to this agent
            active_link = sessions_dir / "active"
            if active_link.exists():
                try:
                    target = active_link.resolve()
                    if agent_id in str(target):
                        active_link.unlink()
                except OSError:
                    pass

        # Clean up conflict reports for this agent
        conflicts_dir = self.agents_dir.parent / "conflicts"
        if conflicts_dir.exists():
            for conflict_file in conflicts_dir.glob(f"{agent_id}_*"):
                try:
                    conflict_file.unlink()
                    logger.debug("Removed conflict file %s", conflict_file)
                except OSError:
                    pass

        # Clean up daily analysis files for this agent
        analysis_dir = self.agents_dir.parent / "analysis"
        if analysis_dir.exists():
            for analysis_file in analysis_dir.glob(f"{agent_id}_*"):
                try:
                    analysis_file.unlink()
                    logger.debug("Removed analysis file %s", analysis_file)
                except OSError:
                    pass

    def agent_exists(self, agent_id: str) -> bool:
        return self._get_agent_file(agent_id).exists()

    def _save_agent(self, agent: AgentInfo) -> None:
        agent_file = self._get_agent_file(agent.agent_id)
        atomic_write_text(
            agent_file,
            json.dumps(agent.model_dump(mode="json"), indent=2),
        )

    def _load_agent_file(self, agent_file: Path) -> AgentInfo | None:
        if not agent_file.exists():
            return None

        with open(agent_file) as f:
            data = json.load(f)
        return AgentInfo(**data)
