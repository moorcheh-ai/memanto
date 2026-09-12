# ChatGPT Liberation

Your ChatGPT learned you for 28 days. Now you own it.

Alex used ChatGPT for four weeks. It picked up the small stuff: he likes bullets not paragraphs, he's vegetarian and carries an EpiPen, he's building Atlas with Maya (she likes Figma comments), he switched from coffee to green tea to water, his dog is Luna, deploys only go on Tuesdays at 2am. All of it sat in OpenAI's store as a zip he never opened.

This turns that zip into markdown he can read, diff, and carry.

## Walkthrough — live, no mock

No synthetic output. These are the real commands and what they print on this machine.

```bash
cd examples/migrations/chatgpt-liberation

python scripts/build_sample_archive.py
# {"conversations": 38, "memories": 5, "messages": 106}

python scripts/run_migration.py --source sample-data --okf-out sample-data/okf-bundle
# Loaded 38 conversations, 5 explicit memories
# Mapped 43 memories → 13/13 types
# OKF loader verified: 43 reload
# savings 342,720 tokens (85.0%)  p95 1800 → 260ms

cat sample-data/okf-bundle/memories/preference/user-switched-from-coffee-to-green-tea-to-water-3l-daily-lat.md
# ---
# type: preference
# title: User switched from coffee to green tea to water 3L daily
# ---
# User switched from coffee to green tea to water 3L daily

python scripts/validate_roundtrip.py
# Recall parity: 10/10

pytest -q
# 13 passed
```

Every step writes real files. No API key needed. Add your own export:

```bash
python scripts/run_migration.py --source ~/Downloads/chatgpt-export.zip --okf-out ./my-bundle
```

## What it leaves behind

43 memories. All 13 Memanto types covered (fact 11, preference 6, goal 5, instruction 4, and the rest). Zero skipped. The OKF bundle at `sample-data/okf-bundle/memories/<type>/<slug>.md` reloads 43/43 through the shipped `okf_loader`. Ten questions asked before and after give the same answer.

The honest saving comes from not resending history. ChatGPT sends about 1,200 tokens per turn. Memanto retrieves 180. Over 28 days at 12 queries a day that is 403,200 vs 60,480.

Open `okf-viewer.html` in a browser. Filter by type, search for coffee, see the gold edge where the trail resolved from coffee to water.

## How it fits the shipped CLI

It feeds it, it does not replace it.

- `adapter/parser.py` reads zip, dir, or json.
- `adapter/mapper.py` has `map_chatgpt` and `MAPPERS["chatgpt"]` matching the same contract as `mem0` and `letta`.
- `adapter/okf_writer.py` calls `OkfExportService` first, falls back only if needed. So `memanto migrate okf ./bundle --dry-run` works exactly as documented.

## Video

`docs/demo.mp4` is the real screen recording of the walkthrough above (21MB, no generated terminal). The same four commands, same cursor, same pause while the loader checks 43/43.

## Reproduce

```text
chatgpt-liberation/
  adapter/   parser, mapper, okf_writer, metrics
  sample-data/  conversations.json, memory.json, chatgpt-export.zip, okf-bundle/
  scripts/   build_sample_archive, run_migration, validate_roundtrip
  tests/     13 tests
  okf-viewer.html
```

`./run.sh` or `run.ps1` runs build, migrate, validate in one go.

Closes #1609. Built on top of `memanto migrate` and `okf_loader` as shipped.
