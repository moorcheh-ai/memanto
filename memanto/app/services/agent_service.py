"""
Agent Service for MEMANTO

Handles agent creation, listing, and lifecycle management.
"""

import json
from datetime import datetime
from pathlib import Path

from moorcheh_sdk.exceptions import ConflictError

from memanto.app.clients.moorcheh import MoorchehClient
from memanto.app.core import create_memory_scope
from memanto.app.models.session import AgentCreate, AgentInfo, AgentList
from memanto.app.utils.errors import AgentAlreadyExistsError, AgentNotFoundError


class AgentService:
    """Service for managing agents"""

    def __init__(self, agents_dir: Path | None = None):
        """
        Initialize agent service

        Args:
            agents_dir: Directory for agent metadata storage (defaults to ~/.memanto/agents/)
        """
        self.agents_dir = agents_dir or Path.home() / ".memanto" / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

    def _generate_namespace(self, agent_id: str) -> str:
        """
        Generate namespace for agent using core MemoryScope

        Format: memanto_{scope}_{scope_id}
        """
        scope = create_memory_scope(scope_type="agent", scope_id=agent_id)
        return scope.to_namespace()

    def _get_agent_file(self, agent_id: str) -> Path:
        """Get file path for agent metadata"""
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

        namespace = self._generate_namespace(agent_create.agent_id)

        # Create namespace in Moorcheh - CRITICAL: Must succeed
        client = MoorchehClient(moorcheh_api_key)

        try:
            # Use Moorcheh SDK to create namespace with type="text"
            client.namespaces.create(namespace, type="text")
            print(f"[OK] Namespace created in Moorcheh: {namespace}")
        except ConflictError:
            # Namespace already exists - this is OK, agent might have been created before
            print(f"[OK] Namespace already exists in Moorcheh: {namespace}")
        except Exception as e:
            # Unexpected error - fail the agent creation
            raise Exception(
                f"Failed to create namespace '{namespace}' in Moorcheh: {str(e)}"
            )

        # Create agent metadata
        agent = AgentInfo(
            agent_id=agent_create.agent_id,
            namespace=namespace,
            pattern=agent_create.pattern,
            description=agent_create.description,
            created_at=datetime.utcnow(),
            memory_count=0,
            session_count=0,
            status="ready",
        )

        # Save agent metadata
        self._save_agent(agent)

        return agent

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

        with open(agent_file) as f:
            data = json.load(f)
            return AgentInfo(**data)

    def list_agents(self) -> AgentList:
        """
        List all agents

        Returns:
            AgentList with all agents
        """
        agents = []
        for agent_file in self.agents_dir.glob("*.json"):
            with open(agent_file) as f:
                data = json.load(f)
                agents.append(AgentInfo(**data))

        # Sort by created_at (newest first)
        agents.sort(key=lambda a: a.created_at, reverse=True)

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
            AgentNotFoundError: If agent doesn't exist
        """
        agent_file = self._get_agent_file(agent_id)
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
        with open(agent_file, "w") as f:
            json.dump(agent.model_dump(mode="json"), f, indent=2)
