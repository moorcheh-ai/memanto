# ChatGPT to Memanto OKF Migration

Liberate the memory your assistant has built about you! This migration adapter converts a standard ChatGPT data export into a Memanto **Open Knowledge Format (OKF)** bundle, allowing you to seamlessly port your entire conversation history into your local Memanto storage.

## Features
- Preserves the chronological conversation threads (User vs Assistant).
- Transforms each conversation into a Markdown file wrapped in OKF frontmatter.
- Compatible directly with `memanto migrate okf`.
- Automatic timestamp and title inference.

## Prerequisites
1. Request your ChatGPT data export from **Settings > Data Controls > Export**.
2. Download and extract the `.zip` file provided by OpenAI.
3. Locate the `conversations.json` file inside the extracted folder.
4. Python 3 installed.

## Usage

**1. Run the adapter to convert your exported conversations into an OKF bundle:**
```bash
python chatgpt_to_okf.py --input /path/to/your/conversations.json --output ./my_okf_bundle
```

**2. Run the official Memanto migration CLI:**
```bash
# Preview the migration (Dry run)
python -m memanto migrate okf ./my_okf_bundle --dry-run

# Run the actual migration
python -m memanto migrate okf ./my_okf_bundle
```

**3. Run the Validation test to verify recall parity:**
```bash
python validate_migration.py
```

## Mapping Table

| ChatGPT Concept | Memanto OKF Concept |
| --- | --- |
| Conversation Thread | OKF Bundle Markdown File |
| Conversation Title | `title` Frontmatter |
| `create_time` | `timestamp` Frontmatter |
| `mapping` (Messages) | `body` (Markdown Content) |
| Conversation | `type: "artifact"` |

## Why OKF?
Once your data is converted to OKF, your memories are stored as readable, portable markdown files. You can track them in `git`, read them in any text editor, and escape vendor lock-in completely. No more stranded memory islands.
