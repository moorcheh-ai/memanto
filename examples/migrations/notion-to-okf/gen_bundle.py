import json, re, sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, '.')
from notion_adapter import map_notion
export = json.loads(Path('data/notion_export.json').read_text(encoding='utf-8'))
rows = map_notion(export)
bundle = Path('sample_okf_bundle/memories')
for row in rows:
    mem_type = row.get('type') or 'fact'
    type_dir = bundle / mem_type
    type_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^a-z0-9-]', '', row['title'][:40].lower().replace(' ', '-').replace('/', '-').replace(':', ''))[:40].strip('-')
    fname = type_dir / f'{slug}.md'
    ts = row['created_at'].isoformat() if row.get('created_at') else datetime.now(timezone.utc).isoformat()
    tags_yaml = '\n'.join(f'  - {t}' for t in row['tags'][:5])
    content = f'---\ntype: {mem_type}\ntitle: "{row["title"][:70]}"\ntimestamp: "{ts}"\ntags:\n{tags_yaml}\nx_memanto:\n  type: {mem_type}\n  source: {row["source"]}\n  confidence: {row["confidence"]}\n  provenance: {row["provenance"]}\n---\n\n{row["content"][:800]}\n'
    fname.write_text(content, encoding='utf-8')
    print(f'  {mem_type}/{fname.name}')
print(f'Done: {len(rows)} files')
