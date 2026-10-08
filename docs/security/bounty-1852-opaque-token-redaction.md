# Opaque token values bypass conversation credential redaction

Related submission: #1852, existing PR #2024.

## Affected boundary

The extraction service sanitizes the `title` and `content` returned in normalized
memory candidates. Its field-name patterns recognized `auth_token`, API keys,
passwords and client secrets, but not `access_token`, `refresh_token`, `id_token`
or `session_token`. The independent provider-prefix, JWT and Bearer patterns do
not recognize arbitrary opaque token values. A candidate containing one of these
ordinary credential fields therefore leaves extraction with the token intact.

This is a credential-redaction failure at the candidate-output boundary. The
reproduction does not establish cross-tenant access, a hosted-backend flaw, an
authentication bypass, or that a particular model will emit a credential. It does
not exercise a database write. It demonstrates what happens when the model
response contains a credential despite the prompt's instruction to omit secrets.

## Reproduction

Affected source was read at carrier commit
`756b876c33a4b50305373a44aae880e689a3c54e`; the extraction-service Git blob is
`7d92da186dd23e583e2d6d48d26d90e3425967f8`.

Supply the normal `answer.generate` boundary with this synthetic response:

```json
{"answer":"[{\"type\":\"fact\",\"title\":\"access_token=synthetic-opaque-credential\",\"content\":\"access_token=synthetic-opaque-credential; scope=read\",\"confidence\":0.9}]"}
```

Call `ConversationMemoryExtractionService.extract` with one valid conversation
message and an explicit model name. Before the patch, both returned fields still
contain `synthetic-opaque-credential`. After the patch, each contains
`[REDACTED_CREDENTIAL]`, and the nonsecret `scope=read` content remains.

The added regression file also exercises JSON properties and single-quoted
assignments, underscore/camel-case/hyphen names, and mixed case. All values are
synthetic; no live credentials or external service are involved.

## Repair

Extend the existing token-name alternative in **both** the quoted and unquoted
credential expressions to `(?:auth|access|refresh|id|session)[_-]?token`.
The existing case-insensitive behavior, value matching, replacements and field
boundaries remain in use. No extraction prompt, client transport, provenance,
confidence, memory type or storage behavior changes.

## Focused validation

Python 3.13.5, pytest 9.0.2:

- Before: **24 failed, 9 passed**.
- After: **33 passed**.
- Network/DNS attempts under rejecting hooks: **0** in both runs.
- Changed production source and new tests pass `py_compile`.

The local run executed the complete byte-identical extraction service, JSON
array parser (blob `35e2a81ead745a1346301905416db4ddb4a0210c`) and constants
(blob `41ecc2557248f33fb31e54b1a09965849f404a4b`). Import-only backend/config
collaborators were inert; the explicit model bypassed model-resolution settings,
and `answer.generate` was an in-memory fixture. This was not a full-package,
live-LLM, backend, persistence, or full repository-suite run. Ruff was unavailable
in that runtime and is not reported as run.

The regression file uses the project's existing pytest interface. In a normally
configured project environment, run:

```bash
python -m pytest tests/test_conversation_token_redaction.py -q
```

Five existing credential-field controls remain redacted, and four controls retain
ordinary token discussion and noncredential metadata such as `token_type`,
`expires_in`, and `refresh_token_count`. The 24 new token cases verify the actual
public `extract` result, both title and content, rather than only the helper.
