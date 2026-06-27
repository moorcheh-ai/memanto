def validate_port(port):
    """Validate that a port number is valid."""
    if not isinstance(port, int):
        return False, "Port must be an integer"
    if port < 1 or port > 65535:
        return False, "Port must be between 1 and 65535"
    if port < 1024:
        return False, "Ports below 1024 require root privileges"
    return True, "OK"
