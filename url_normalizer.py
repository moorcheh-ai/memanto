def normalize_url(url):
    """Normalize a server URL."""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    if url.endswith('/'):
        url = url[:-1]
    return url
