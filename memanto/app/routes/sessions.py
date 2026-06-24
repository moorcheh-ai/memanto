"""
Session and Agent Lifecycle Routes

New session-based architecture endpoints.
Replaces tenant_id with Moorcheh API key-based authentication.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from memanto.app.clients import moorcheh as moorcheh_clients
from memanto.app.config import settings
from memanto.app.models.session import (
    AgentCreate,
    AgentInfo,
    AgentList,
    Session,
    SessionInfo,
    SessionSummary,
)
from memanto.app.services.agent_service import AgentService
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    SessionNotFoundError,
    map_error_to_http_exception,
)

router = APIRouter()

# Import auth dependencies (avoid circular import)
# Include memory operations sub-router
# Commented to avoid triggering ruff linter
from memanto.app.routes import memory  # noqa: E402
from memanto.app.routes.auth_deps import (  # noqa: E402
    get_current_session,
    get_moorcheh_api_key,
    get_session_service,
    verify_moorcheh_api_key,
)

router.include_router(memory.router, prefix="/agents", tags=["Memory Operations"])

# Service instances
agent_service = AgentService()


def get_agent_service():
    """Get agent service instance"""
    return agent_service


async def _namespace_item_counts(moorcheh_api_key: str) -> dict[str, int]:
    """Map namespace_name -> live document count from Moorcheh.

    The ``memory_count`` stored in local agent metadata is never updated after
    creation, so it is always 0. Moorcheh tracks the authoritative per-namespace
    document count, which is what the UI should display. Best-effort: returns an
    empty map if Moorcheh is unreachable so agent listing still succeeds.
    """
    try:
        client = moorcheh_clients.get_moorcheh_client()
        ns_resp = await asyncio.to_thread(client.namespaces.list)
        return {
            ns["namespace_name"]: ns.get("item_count", 0)
            for ns in ns_resp.get("namespaces", [])
            if ns.get("namespace_name")
        }
    except Exception:
        return {}


# ============================================================================
# AGENT LIFECYCLE ENDPOINTS
# ============================================================================


@router.post("/agents", response_model=AgentInfo, status_code=201)
async def create_agent(
    agent_create: AgentCreate, moorcheh_api_key: str = Depends(get_moorcheh_api_key)
):
    """
    Create a new MEMANTO agent

    Creates:
    - Agent metadata in ~/.memanto/agents/
    - Moorcheh namespace: memanto_agent_{agent_id}

    The agent is ready to activate once created.
    """
    try:
        agent = agent_service.create_agent(agent_create, moorcheh_api_key)
        return agent
    except AgentAlreadyExistsError as e:
        raise map_error_to_http_exception(e)


@router.get("/agents", response_model=AgentList)
async def list_agents(moorcheh_api_key: str = Depends(verify_moorcheh_api_key)):
    """
    List all agents for this Moorcheh account

    Returns agents sorted by creation date (newest first). The ``memory_count``
    of each agent is populated with the live document count from its Moorcheh
    namespace rather than the stale value in local metadata.
    """
    agent_list = agent_service.list_agents()
    counts = await _namespace_item_counts(moorcheh_api_key)
    for agent in agent_list.agents:
        if agent.namespace in counts:
            agent.memory_count = counts[agent.namespace]
    return agent_list


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(
    agent_id: str, moorcheh_api_key: str = Depends(verify_moorcheh_api_key)
):
    """
    Get agent information

    ``memory_count`` reflects the live document count from the agent's Moorcheh
    namespace.
    """
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise map_error_to_http_exception(
            AgentNotFoundError(f"Agent '{agent_id}' not found")
        )
    counts = await _namespace_item_counts(moorcheh_api_key)
    if agent.namespace in counts:
        agent.memory_count = counts[agent.namespace]
    return agent


@router.delete("/agents/{agent_id}", status_code=200)
async def delete_agent(
    agent_id: str,
    delete_backup_too: bool = Query(
        False, alias="delete-backup-too", description="Delete Moorcheh namespace backup"
    ),
    moorcheh_api_key: str = Depends(verify_moorcheh_api_key),
):
    """
    Delete agent

    Always deletes local agent metadata.
    If `delete-backup-too=true`, also deletes the agent memory namespace in Moorcheh.
    """
    try:
        agent = agent_service.get_agent(agent_id)
        if not agent:
            raise map_error_to_http_exception(
                AgentNotFoundError(f"Agent '{agent_id}' not found")
            )

        if delete_backup_too:
            # Delete remote namespace only when explicitly requested.
            moorcheh_client = moorcheh_clients.get_moorcheh_client()
            try:
                moorcheh_client.namespaces.delete(namespace_name=agent.namespace)
            except Exception:
                # If namespace is already gone/unreachable, keep best-effort behavior
                # and continue removing local metadata.
                pass

        agent_service.delete_agent(agent_id)
        return {
            "message": (
                f"Agent '{agent_id}' successfully deleted"
                + (
                    " with all namespace memories"
                    if delete_backup_too
                    else " (backup retained in Moorcheh)"
                )
            )
        }
    except AgentNotFoundError as e:
        raise map_error_to_http_exception(e)


# ============================================================================
# SESSION LIFECYCLE ENDPOINTS
# ============================================================================


@router.post("/agents/{agent_id}/activate", response_model=Session)
async def activate_agent(
    agent_id: str,
    moorcheh_api_key: str = Depends(verify_moorcheh_api_key),
):
    """
    Activate agent and start session

    Creates:
    - JWT session token (6-hour expiration by default, configurable)
    - Session file in ~/.memanto/sessions/
    - Active session marker

    Returns session token for use in memory operations.
    """
    # Check if agent exists
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise map_error_to_http_exception(
            AgentNotFoundError(f"Agent '{agent_id}' not found")
        )

    # Session duration is controlled by server defaults.
    duration_hours = settings.SESSION_DEFAULT_DURATION_HOURS

    try:
        session = get_session_service().create_session(
            agent_id=agent_id,
            pattern=agent.pattern,
            duration_hours=duration_hours,
        )

        # Update agent stats
        agent_service.update_agent_stats(
            agent_id=agent_id,
            last_session=session.started_at,
            increment_session_count=True,
        )

        return session

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/agents/{agent_id}/deactivate", response_model=SessionSummary)
async def deactivate_agent(
    agent_id: str,
    session: Session = Depends(get_current_session),
    _server_api_key: str = Depends(verify_moorcheh_api_key),
):
    """
    Deactivate agent and end session

    Terminates the current session and returns statistics.
    Requires X-Session-Token header and matching agent_id.
    """
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        summary = get_session_service().end_session(agent_id)
        return summary
    except SessionNotFoundError as e:
        raise map_error_to_http_exception(e)


@router.get("/status", response_model=SessionInfo)
async def get_status():
    """
    Get current active session status.

    No parameters required — reads the active session from local state.
    """
    session = get_session_service().get_active_session()
    if session is None:
        raise HTTPException(status_code=404, detail="No active session")

    time_remaining = session.time_remaining()

    return SessionInfo(
        session_id=session.session_id,
        agent_id=session.agent_id,
        namespace=session.namespace,
        started_at=session.started_at,
        expires_at=session.expires_at,
        status=session.status,
        time_remaining_seconds=max(0, int(time_remaining.total_seconds())),
        pattern=session.pattern,
    )
