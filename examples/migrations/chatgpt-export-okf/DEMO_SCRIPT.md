# Two-minute demo script

This script supports a truthful public submission. Replace every placeholder
with a real run from an export that you are permitted to use.

1. Show the local, unzipped ChatGPT data-export folder without exposing file
   contents or identifying names.
2. Run `python run_demo.py --export <real-export> --out artifacts` and show
   the generated `memory_count`, redaction state, and successful validation.
3. Open `artifacts/okf/index.md` and one redacted event file. Highlight the
   readable conversation context, provenance fields, and checksum manifest.
4. Run `memanto migrate okf artifacts/okf --dry-run`; show the preview, not
   secret configuration or raw personal content.
5. Configure a dedicated test agent, complete the real import, and use
   `memanto memory export --okf` to create a second bundle.
6. Show a small, manually reviewed golden-Q&A set against the original export
   and the imported agent. Report disagreements honestly rather than claiming
   byte-identical semantic recall.
7. End with the bundle's folder tree and repository instructions so viewers
   can run the converter themselves.

Before publishing: scrub the terminal history, input path, raw export, API
keys, emails, wallet addresses, browser tabs, and account profile details.
