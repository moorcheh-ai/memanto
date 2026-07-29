# sessions.py — /status endpoint now requires authentication (fix #1436)
# BEFORE: no Depends at all → leaks active agent_id, session_id, expires_at
# AFTER:  requires get_current_session → caller must present valid session token

from fastapi import APIRouter, Depends
from memanto.app.core.session import Session, get_current_session

router = APIRouter()

@router.get("/api/v2/status")
def get_status(session: Session = Depends(get_current_session)):
    """
    Returns current session info.
    Now requires a valid session token — previously was fully unauthenticated
    (reported in Bug Challenge #770 / Issue #1436).
    """
    return {
        "agent_id":   session.agent_id,
        "session_id": session.session_id,
        "namespace":  session.namespace,
        "started_at": session.started_at.isoformat() if hasattr(session.started_at, "isoformat") else str(session.started_at),
        "expires_at": session.expires_at.isoformat() if hasattr(session.expires_at, "isoformat") else str(session.expires_at),
    }
