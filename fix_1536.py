import os
import json
import re
import tempfile

def validate_safe_id(agent_id):
    """Validate agent ID to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]+$', agent_id):
        raise ValueError("Invalid agent ID")

def create_session_directory(agent_id):
    validate_safe_id(agent_id)
    session_dir = os.path.join(os.path.expanduser('~/.memanto/sessions'))
    os.makedirs(session_dir, exist_ok=True)
    # Harden permissions for existing directories
    os.chmod(session_dir, 0o700)
    return session_dir

def create_session_file(agent, session_token):
    validate_safe_id(agent)
    session_dir = create_session_directory(agent)
    session_file = os.path.join(session_dir, f'{agent}.json')
    
    # Use os.open to correctly apply 0o600 permissions
    fd = os.open(session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'session_token': session_token}, f)
    
    # Preserve active-session symlink behavior
    active_link = os.path.join(session_dir, 'active_session')
    if os.path.islink(active_link) or os.path.exists(active_link):
        os.remove(active_link)
    os.symlink(session_file, active_link)
    
    return session_file

def update_session_file(agent, session_token):
    validate_safe_id(agent)
    session_dir = create_session_directory(agent)
    session_file = os.path.join(session_dir, f'{agent}.json')
    temp_file = os.path.join(session_dir, f'{agent}.tmp')
    
    try:
        # Use os.open for correct permissions on temp file
        fd = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'session_token': session_token}, f)
            f.flush()
            os.fsync(f.fileno()) # Ensure flushed and synchronized
            
        os.replace(temp_file, session_file)
        
        # Update symlink
        active_link = os.path.join(session_dir, 'active_session')
        if os.path.islink(active_link) or os.path.exists(active_link):
            os.remove(active_link)
        os.symlink(session_file, active_link)
        
    except Exception:
        # Clean up temp file on failure, suppressing OSError to prevent masking the original exception
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        raise

if __name__ == "__main__":
    create_session_file("agent_1", "token_123")
    update_session_file("agent_1", "token_456")
