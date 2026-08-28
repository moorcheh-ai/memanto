"""Regression tests for the Langfuse SSRF guard (bounty #1852).

normalize_host() must never steer Memanto's server-side fetch (which carries
the Langfuse secret key as Basic auth) at internal infrastructure. Public
self-hosted domains are allowed; private/loopback/link-local/metadata hosts are
rejected and fall back to the official cloud default.
"""

from memanto.cli.analyze.langfuse_export import normalize_host, DEFAULT_HOST


def test_cloud_regions_allowed():
    assert normalize_host("https://cloud.langfuse.com") == "https://cloud.langfuse.com"
    assert normalize_host("https://us.cloud.langfuse.com") == "https://us.cloud.langfuse.com"
    assert normalize_host("https://eu.cloud.langfuse.com") == "https://eu.cloud.langfuse.com"


def test_none_falls_back_to_default():
    assert normalize_host(None) == DEFAULT_HOST


def test_loopback_host_rejected():
    # Would otherwise exfiltrate the secret key to localhost.
    assert normalize_host("http://127.0.0.1:9000") == DEFAULT_HOST
    assert normalize_host("http://localhost:9000") == DEFAULT_HOST


def test_metadata_endpoint_rejected():
    # Cloud metadata endpoint — classic SSRF credential-theft target.
    assert normalize_host("http://169.254.169.254/latest/meta-data/") == DEFAULT_HOST


def test_rfc1918_rejected():
    # Internal corporate addresses must not be reachable.
    assert normalize_host("http://10.0.0.5") == DEFAULT_HOST
    assert normalize_host("http://192.168.1.10:8080") == DEFAULT_HOST


def test_public_selfhost_allowed(monkeypatch):
    # A real public self-hosted domain (resolves to a public IP) is allowed.
    # Patch getaddrinfo so the test is deterministic/offline-safe.
    import socket

    def _fake_getaddrinfo(host, port, *a, **k):
        # Return a public IPv4 (8.8.8.8 is a real public address) for any host.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    out = normalize_host("https://langfuse.example.com")
    assert out == "https://langfuse.example.com"
