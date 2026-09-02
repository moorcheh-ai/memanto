## Security hardening: authorization and memory boundaries

### Summary

This PR strengthens authorization boundaries, backend-response handling, and
memory prompt safety.

Full sensitive reproduction details were privately disclosed to
support@moorcheh.ai.

### Changes

- Management: reject remote clients forwarded through loopback proxies and
  cross-site UI requests.
- Scope: require session-bound agent scope for memory and policy operations;
  prevent unscoped namespace enumeration.
- Disclosure: use server credentials upstream, redact backend citations, hide
  answer namespaces, and return generic provider errors.
- Prompt safety: neutralize control markers and JSON-frame untrusted extraction
  payloads.
- Tests: add regression coverage for proxy auth, scope, disclosure, policy, and
  prompt boundaries.

### API contract notice

The internal namespace value has intentionally been removed from the public
answer response.

### Testing

    DEBUG=false uv run pytest \
      tests/test_memory_scope_and_answer_security.py \
      tests/test_api.py::TestMEMANTOAPI::test_answer_omits_namespace_and_sanitizes_provider_failure \
      tests/test_api.py::TestMEMANTOAPI::test_answer_redacts_raw_backend_source_metadata \
      tests/test_conversation_memory_extraction.py -q
    # 12 passed

- ruff check passed
- ruff format --check passed
- git diff --check passed
