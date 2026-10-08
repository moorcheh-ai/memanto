# Basic authentication survives conversation extraction

Refs #1852. This repair is included in the existing PR #2024.

## Finding and preconditions

At parent `18db2221e95ef3f6b414fe849ee0face535ce323`, the conversation sanitizer recognizes Bearer, provider-shaped and named credentials but leaves Basic authentication values intact. If an answer response repeats an Authorization or Proxy-Authorization value from a conversation, the real extraction service returns the credential in both the candidate title and content. A Basic value commonly contains an encoded username/password pair.

This is a package-side redaction failure. The reproduction uses a synthetic answer client and synthetic credentials. It does not establish that a live model repeats a credential, that the returned candidate was subsequently persisted, or that a hosted backend or another tenant was compromised.

## Repair

`memanto/app/services/conversation_memory_extraction_service.py` now recognizes Basic values attached to Authorization and Proxy-Authorization fields and removes the complete opaque credential. It preserves the field name, scheme, surrounding quoted JSON/config text and unrelated metadata. Repeated sanitization keeps the same replacement marker.

Field/scheme matching uses ASCII case folding. The prefix does not cross header lines, and whitespace around an optional opening quote is consumed without overlapping repetitions. The existing Bearer, provider, URL, PEM and named-field rules are retained.

## Reproduction and maintained regressions

A minimal synthetic payload is:

```python
import json
from types import SimpleNamespace
from memanto.app.services.conversation_memory_extraction_service import (
    ConversationMemoryExtractionService,
)

credential = "dXNlcjpzeW50aGV0aWMtcGFzc3dvcmQ="
text = "Authorization: Basic " + credential
answer = json.dumps([{"type": "fact", "title": text, "content": text}])
client = SimpleNamespace(answer=SimpleNamespace(generate=lambda **kwargs: {"answer": answer}))
candidate = ConversationMemoryExtractionService(client).extract(
    namespace="memanto_agent_test",
    messages=[{"role": "user", "content": "Remember the authentication setup."}],
    ai_model="synthetic-model",
)[0]
assert credential not in candidate["title"]
assert credential not in candidate["content"]
```

The same response is used as title and content. Before repair the two assertions fail. After repair both fields contain `Authorization: Basic [REDACTED_CREDENTIAL]`.

Two maintained functions were added to `tests/test_conversation_token_redaction.py`: `test_extract_redacts_basic_authentication_in_title_and_content` and `test_basic_auth_redaction_preserves_noncredential_text`. The first covers a plain header, quoted JSON and mixed-case proxy/config text with a complete opaque suffix; it also checks JSON decoding, metadata, the answer call count and idempotence. The second preserves a Basic challenge, an unrelated X-Authorization field, an incomplete header followed by a new line, and ordinary prose.

With the repository's normal test dependencies installed, run only these additions with:

```bash
python -m pytest -q tests/test_conversation_token_redaction.py -k basic_auth
```

## Execution evidence

CPython 3.12.14 executed the complete production extraction module and the unchanged production constants and JSON-array parser. Only the configuration/backend-model import collaborators were isolated; an explicit synthetic model bypassed model lookup, and the in-memory answer client returned the controlled response. No package installation or live model/backend was used.

| Check | Parent source | Repaired source |
| --- | --- | --- |
| Plain Authorization header | Credential survives title and content | Both fields redacted |
| Quoted Authorization JSON | Credential survives title and content | Both fields redacted; JSON preserved |
| Proxy-Authorization config | Credential survives title and content | Both fields redacted |
| Two newly maintained functions, called directly | Not run as maintained functions | Completed successfully: three extraction formats and four unchanged controls |
| 120,021-character malformed prefix, including 120,000 spaces | Not timed | Unchanged in 0.0192 seconds, one local sample |

The malformed-prefix measurement checks one adversarial input; it is not a scaling benchmark or an end-to-end latency result.

Source SHA-256 values for the complete extraction module:

- Parent: `34fd17156c64526502e9eeed1daf0b952583e1073525ab6a98c42d5bacaeaff5`.
- Repaired: `3af654070fe99633b704608724ceabd0e7bc1f1de09f8c9ef13fc99cf2db51d9`.

The two maintained functions were compiled and invoked directly with the actual extraction service and sanitizer. Pytest and the repository fixtures were not available in that isolated environment, so the pytest command above is the maintainer reproduction command, not an executed pytest result. This evidence does not replace earlier source-specific validation or establish a full-suite result for the cumulative PR.

Coverage is literal same-line header/config and quoted JSON fields. Additional serialization layers with escaped delimiters, malformed multiline credentials and other authentication schemes are outside the demonstrated guarantee.
