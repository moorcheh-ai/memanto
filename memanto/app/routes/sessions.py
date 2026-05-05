"""
Session and Agent Lifecycle Routes

New session-based architecture endpoints.
Replaces tenant_id with Moorcheh API key-based authentication.
"""

from fastapi import APIRouter, Depends, HTTPException

from memanto.app.config import settings
from memanto.app.models.session import (
    AgentCreate,
    AgentInfo,
    AgentList,
    Session,
    SessionCreate,
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
from memanto.app.routes import memory_v2  # noqa: E402
from memanto.app.routes.auth_deps import (  # noqa: E402
    get_current_session,
    get_session_service,
    verify_moorcheh_api_key,
)

router.include_router(
    memory_v2.router, prefix="/agents", tags=["Memory Operations (V2)"]
)

# Service instances
agent_service = AgentService()


def get_agent_service():
    """Get agent service instance"""
    return agent_service


# ============================================================================
# AGENT LIFECYCLE ENDPOINTS
# ============================================================================


@router.post("/agents", response_model=AgentInfo, status_code=201)
async def create_agent(
    agent_create: AgentCreate, moorcheh_api_key: str = Depends(verify_moorcheh_api_key)
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

    Returns agents sorted by creation date (newest first).
    """
    return agent_service.list_agents()


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(
    agent_id: str, moorcheh_api_key: str = Depends(verify_moorcheh_api_key)
):
    """
    Get agent information
    """
    agent = agent_service.get_agent(agent_id)
    if not agent:
        raise map_error_to_http_exception(
            AgentNotFoundError(f"Agent '{agent_id}' not found")
        )
    return agent


@router.delete("/agents/{agent_id}", status_code=200)
async def delete_agent(
    agent_id: str, moorcheh_api_key: str = Depends(verify_moorcheh_api_key)
):
    """
    Delete agent

    Warning: This does NOT delete memories from Moorcheh.
    Only removes local agent metadata.
    """
    try:
        agent_service.delete_agent(agent_id)
        return {"message": f"Agent '{agent_id}' successfully deleted"}
    except AgentNotFoundError as e:
        raise map_error_to_http_exception(e)


# ============================================================================
# SESSION LIFECYCLE ENDPOINTS
# ============================================================================


@router.post("/agents/{agent_id}/activate", response_model=Session)
async def activate_agent(
    agent_id: str,
    session_create: SessionCreate | None = None,
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

    # Get duration from request or use default
    duration_hours = (
        session_create.duration_hours
        if session_create
        else settings.SESSION_DEFAULT_DURATION_HOURS
    )

    try:
        session = get_session_service().create_session(
            agent_id=agent_id,
            moorcheh_api_key=moorcheh_api_key,
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
    agent_id: str, moorcheh_api_key: str = Depends(verify_moorcheh_api_key)
):
    """
    Deactivate agent and end session

    Terminates the current session and returns statistics.
    """
    try:
        summary = get_session_service().end_session(agent_id)
        return summary
    except SessionNotFoundError as e:
        raise map_error_to_http_exception(e)


@router.get("/session/current", response_model=SessionInfo)
async def get_current_session_info(session: Session = Depends(get_current_session)):
    """
    Get current session information

    Requires X-Session-Token header.
    """
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


@router.post("/session/extend", response_model=Session)
async def extend_session(
    additional_hours: int = settings.SESSION_DEFAULT_DURATION_HOURS,
    session: Session = Depends(get_current_session),
):
    """
    Extend current session expiration

    Adds additional hours to session expiration.
    """
    if additional_hours <= 0:
        raise HTTPException(
            status_code=422, detail="Additional hours must be greater than 0."
        )

    try:
        extended_session = get_session_service().extend_session(
            session.agent_id, additional_hours
        )
        return extended_session
    except SessionNotFoundError as e:
        raise map_error_to_http_exception(e)


@router.get("/sessions", response_model=list[Session])
async def list_sessions(moorcheh_api_key: str = Depends(verify_moorcheh_api_key)):
    """
    List all sessions

    Returns sessions sorted by start time (newest first).
    """
    return get_session_service().list_sessions()
