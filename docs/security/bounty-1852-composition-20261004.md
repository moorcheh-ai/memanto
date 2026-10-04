# Bounty 1852: focused composition result, 2026-10-04

## Result

**60 passed, 0 failed, 0 errors, 0 skipped; pytest exit 0.** The tests ran together in one fresh environment with the repository's original `pytest.ini` and `tests/conftest.py`. Pytest reported **0.70 seconds**; JUnit recorded **0.697 seconds**. This is test execution time, not an application-performance benchmark.

- Tested source: `79f6ee17c06496b53a2652a8033ba77b3d83f599`.
- This documentation-only source revision follows cumulative product `5a695228728ee4b7439479a87783c737639ec31a`.
- Execution-only workflow commit: `f3b55e1901a2e209c10794cffe5c8ce7a19e25fc` on `validation/kestrel-1004-memanto-composition`. The workflow explicitly checked out the tested source above, not its own commit.
- [Completed GitHub Actions run 37189951329](https://github.com/woahwhattheheck/memanto/actions/runs/37189951329), job `111399866655`, conclusion `success`.
- [Exact executable workflow](https://github.com/woahwhattheheck/memanto/blob/f3b55e1901a2e209c10794cffe5c8ce7a19e25fc/.github/workflows/memanto-1852-composition.yml).
- The original submission remains [moorcheh-ai/memanto#2024](https://github.com/moorcheh-ai/memanto/pull/2024), branch `fix/1852-local-sync-scope-20260920`. This execution did not modify that branch or post a second upstream submission.

## Selected existing coverage

| Selection | Cases |
| --- | ---: |
| `tests/test_client_session_agent_scope.py` | 22 |
| `tests/test_conversation_token_redaction.py` | 33 |
| Five named `TestSessionService` creation/active-marker cases below | 5 |
| Total actually collected and executed together | 60 |

The first file covers both real client classes, cross-agent token rejection, token/cache replacement, expired matching and nonmatching sessions, matching renewal, and persisted logout/delete/replacement with auto-renew enabled and disabled. The second exercises actual extraction results for opaque credential fields and noncredential controls. The five unit cases cover normal session creation, marker-read synchronization, the cross-agent marker interleaving, private text fallback, and failed marker replacement cleanup.

These are the existing test files and fixtures; no test implementation or application source was replaced. The package was installed editable from the pinned checkout. The installation generated its ordinary VCS-derived version file and identified the package as `0.0.1.dev1+g79f6ee17c`.

## Exact selection and configuration

The workflow's Python wrapper invoked `pytest.main` with the arguments equivalent to:

```bash
python -m pytest -c pytest.ini -vv -ra -p no:cacheprovider \
  --import-mode=importlib --junitxml="$RUNNER_TEMP/memanto-composition.xml" \
  tests/test_client_session_agent_scope.py \
  tests/test_conversation_token_redaction.py \
  tests/test_unit.py::TestSessionService::test_create_session \
  tests/test_unit.py::TestSessionService::test_active_session_read_waits_for_marker_update \
  tests/test_unit.py::TestSessionService::test_active_marker_interleaving_preserves_other_agent_session \
  tests/test_unit.py::TestSessionService::test_active_marker_text_fallback_preserves_sessions \
  tests/test_unit.py::TestSessionService::test_active_marker_replace_failure_keeps_previous_marker
```

The exact workflow also isolates `HOME`, sets the synthetic `MOORCHEH_API_KEY=test-api-key`, and installs a Python audit hook before importing pytest. The hook rejects `socket.connect`, `socket.getaddrinfo`, `socket.gethostbyname`, and `socket.gethostbyaddr`, and makes the run fail if any of these events occur even if an individual test catches the exception. **Observed events: `[]`.** This observation applies to the guarded test process, not the network-enabled checkout/dependency-install steps or an OS-wide traffic measurement. The repository's existing mocked backend and answer fixtures remain in use; no hosted backend or live model was invoked by the selected cases.

Environment preparation used one new venv and the package's declared test dependency ranges:

```bash
python -m venv "$RUNNER_TEMP/memanto-composition-venv"
"$RUNNER_TEMP/memanto-composition-venv/bin/python" -m pip install -e . \
  'pytest>=8.2.0,<9' 'pytest-asyncio>=0.21.0' \
  'pytest-mock>=3.12.0,<4' 'pytest-timeout>=2.1.0'
```

No `uv.lock` exists at this source revision; dependency resolution was fresh rather than locked. The exact resolved versions are retained below and in the job log.

## Runtime and source hashes

- CPython `3.12.14 (main, Aug 13 2026, 02:47:42) [GCC 13.3.0]`.
- Ubuntu 24.04.5; runner image `ubuntu-24.04`, image version `20260927.320.1`.
- Kernel `Linux 6.17.0-1022-azure x86_64 GNU/Linux`.
- Pytest `8.4.2`; loaded plugins `asyncio-1.4.0`, `timeout-2.4.0`, `mock-3.16.0`, `anyio-4.15.1`.
- Original configuration loaded: `pytest.ini`, strict markers/config, asyncio auto, 300-second per-test timeout.
- Standard public-repository GitHub-hosted runner; job permission `contents: read`, checkout credentials removed before execution, no owner-PC runner.

SHA-256 values printed by the job:

```text
fce32387f608a16ed84f20c25b7dc9d1c864e4ddc116c3c90c4945522b7d3d4b  pytest.ini
789fedd2a40672f021ad9d05eb6b1125f063cda523572fa38f26e84c2e715068  pyproject.toml
42c2eb20e4a5fbea55c482e353f0182ba519749721d7aa05417c76731aae59eb  tests/conftest.py
c43958723777b34beeb82c3cd660f5a8e2ccddd71b56ca65167234b89e899311  tests/test_client_session_agent_scope.py
fb795f5373c922cc66a8167339f431262b83eeed4d53d0db466cc65a98b06659  tests/test_conversation_token_redaction.py
d17765d159bd3bb3b917b491c620256c01d04e00883fdb2c34a4b376bdff1ca6  tests/test_unit.py
```

## Resolved dependency snapshot

```text
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.7.22
click==8.5.0
fastapi==0.142.2
filelock==4.0.10
h11==0.16.0
httpcore==1.0.9
httptools==0.8.0
httpx==0.28.1
idna==3.20
iniconfig==2.3.0
markdown-it-py==4.2.0
mdurl==0.1.2
-e git+https://github.com/woahwhattheheck/memanto@79f6ee17c06496b53a2652a8033ba77b3d83f599#egg=memanto
moorcheh-sdk==1.3.7
opentelemetry-api==1.45.0
packaging==26.3
pluggy==1.6.0
pydantic==2.13.5
pydantic-settings==2.15.0
pydantic_core==2.46.5
Pygments==2.21.0
PyJWT==2.15.1
pytest==8.4.2
pytest-asyncio==1.4.0
pytest-mock==3.16.0
pytest-timeout==2.4.0
python-dotenv==1.2.4
python-multipart==0.0.32
PyYAML==6.0.3
RapidFuzz==3.14.6
rich==15.0.0
shellingham==1.5.4
starlette==1.7.0
typer==0.27.2
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.54.0
uvloop==0.23.0
watchfiles==1.3.0
websockets==17.2
```

## Interpretation

This closes the requested composition-evidence gap for these three selected areas at the pinned cumulative head: the earlier separately tested repairs also pass together under the real package/test configuration and supported pytest major version. It is not a full-suite result, an application-throughput benchmark, proof of every other repair on the branch, a hosted-service exploit or acceptance, or evidence of an award/payment. Prior component counts overlap this run and must not be added to 60.

The source claims and single upstream carrier are unchanged. No rerun or duplicate verification is needed absent a relevant source change or a specific maintainer request.
