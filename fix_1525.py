from fastapi import HTTPException, status

class AgentError(Exception):
    pass

def map_error_to_http_exception(exc):
    # 1. Add passthrough for HTTPException to prevent overriding status codes
    if isinstance(exc, HTTPException):
        return exc
    # 2. Handle domain-specific errors
    if isinstance(exc, AgentError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    # 3. Fallback for unexpected failures
    elif isinstance(exc, Exception):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")
    else:
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unknown Error")

def create_agent(data):
    # Simulate a plan limit conflict
    if data.get("plan", 0) > 4:
        raise AgentError("Agent creation limit reached for this plan.")
    return {"id": 1, "data": data}

def get_agent(agent_id):
    return {"id": agent_id}

def list_agents():
    return []

def delete_agent(agent_id):
    return {"deleted": agent_id}

def sessions():
    try:
        # agent lifecycle and status route endpoints logic here
        create_agent({"plan": 5})
        get_agent(1)
        list_agents()
        delete_agent(1)
    except Exception as e:
        # This will now correctly preserve the 409 Conflict if raised
        raise map_error_to_http_exception(e)
