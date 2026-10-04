# Quoted credential keys bypass extraction redaction

This follow-up belongs to issue #1852 and the existing PR #2024. It repairs the
credential-redaction boundary in extracted conversation memory candidates.

## Baseline

The source and existing test file were read at PR head
`3d3b0eceb970744d501ccfea73b4d3f0ae47af53`:

| File | Original Git blob |
| --- | --- |
| `memanto/app/services/conversation_memory_extraction_service.py` | `f767cf9dc95b8ce037f0e5446b487cad4e3dc5a8` |
| `tests/test_conversation_memory_extraction.py` | `ff2e9e74933510f664727de537421265206851bb` |

## Finding and reproduction

The existing key/value credential expressions required a recognized key to be
followed immediately by whitespace and `:` or `=`. A JSON field's closing quote
therefore prevented a match. A provider credential or password without a
separately recognizable token prefix could remain in the returned candidate.

1. Use the test file's existing `FakeClient` to return a JSON array containing a
   memory candidate with this text in both `title` and `content`:
   `{"MOORCHEH_API_KEY": "mk_json_marker", "mode": "safe"}`.
2. Call `ConversationMemoryExtractionService(client).extract()` with one normal
   user message and a test namespace.
3. On the baseline, the returned title still contains `mk_json_marker`. The
   content passes through the same redactor and retains the credential too.
   A quoted `password` field has the same failure.
4. After the repair, both fields contain `[REDACTED_CREDENTIAL]` in place of the
   complete credential value; the surrounding text and `mode` field stay intact.

All reproduction values are synthetic. The added regression uses the actual
`extract()` entry point, JSON response parsing, and candidate normalization;
only the existing answer client is a fake.

## Patch

Both key/value expressions now accept a closing quote after an already
recognized credential key. That quote stays in the preserved prefix capture;
the opening quote remains untouched in the surrounding text. The recognized
key list, case handling, replacement groups, and bare environment variable
assignments remain supported.

The quoted-value expression consumes backslash escape pairs before looking for
the closing delimiter. This prevents an escaped quote from ending the match
early and leaving a credential suffix behind. The regression covers JSON
provider/password keys, escaped quotes and backslashes, a trailing escaped
backslash, single quote variants, and an unquoted numeric JSON value. Every
case asserts the complete returned title and content, including adjacent text.

## Focused validation

Python 3.12.14:

| Source under test | Result |
| --- | --- |
| Pinned baseline source with the seven added regressions | 7 failed, 12 deselected in 0.49 s |
| Patched source with the entire existing extraction test file | 19 passed in 0.51 s |

The measured run loaded the pinned baseline or patched service module from a
small source overlay and reused installed dependencies and unchanged test
fixtures from checkout `508af7e27cf9efb8e9068814bd85a192c600fb33`. It called pytest
with `--import-mode=importlib`, disabled its cache provider, and ran only
`tests/test_conversation_memory_extraction.py`. Home-directory resolution was
isolated, the provider API key was removed, and socket/DNS operations were
rejected. Both runs recorded zero network attempts. Ruff check and formatting
passed for the two changed Python files.

To repeat the focused file in a checkout containing this patch:

```bash
env -u MOORCHEH_API_KEY PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m pytest -q -p no:cacheprovider \
  --import-mode=importlib tests/test_conversation_memory_extraction.py
```

The observed result establishes redaction of returned extraction candidates.
It does not establish hosted persistence, cross-tenant access, or a full-suite
result at the latest cumulative PR head. The redactor continues to recognize
its existing credential formats; it is not a general detector for arbitrary
secret text.
