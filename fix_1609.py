import os
import sys
import json
import argparse
import yaml
from typing import List, Dict, Any

class MemoryMigrator:
    """CLI for migrating agentic memories to the OKF format."""

    def __init__(self, source: str, okf_dir: str = "okf_exports"):
        self.source = source.lower()
        self.okf_dir = okf_dir
        if not os.path.exists(self.okf_dir):
            os.makedirs(self.okf_dir)

    def migrate_from_mem0(self) -> List[Dict[str, Any]]:
        # Simulated migration logic from Mem0
        print("Simulating migration from Mem0...")
        return [{"id": "mem0_1", "content": "User likes pizza", "type": "fact"}]

    def migrate_from_letta(self) -> List[Dict[str, Any]]:
        # Simulated migration logic from Letta
        print("Simulating migration from Letta...")
        return [{"id": "letta_1", "content": "Agent is helpful", "type": "behavior"}]

    def migrate_from_supermemory(self) -> List[Dict[str, Any]]:
        # Simulated migration logic from Supermemory
        print("Simulating migration from Supermemory...")
        return [{"id": "sm_1", "content": "Project uses Python", "type": "tech"}]

    def export_memory(self, use_okf: bool = False):
        memories: List[Dict[str, Any]] = []
        
        if self.source == 'mem0':
            memories = self.migrate_from_mem0()
        elif self.source == 'letta':
            memories = self.migrate_from_letta()
        elif self.source == 'supermemory':
            memories = self.migrate_from_supermemory()
        else:
            sys.exit(f"Unsupported source: {self.source}")

        okf_file = os.path.join(self.okf_dir, 'memory.okf')
        
        if use_okf:
            # Simulate OKF bundle format (YAML frontmatter + body)
            with open(okf_file, 'w', encoding='utf-8') as f:
                for mem in memories:
                    f.write("---\n")
                    yaml.dump({'id': mem['id'], 'type': mem['type']}, f)
                    f.write("---\n")
                    f.write(f"{mem['content']}\n\n<!-- okf-entry -->\n")
            print(f"Exported to OKF bundle at {okf_file}")
        else:
            # Raw JSON export fallback
            json_file = os.path.join(self.okf_dir, 'memory.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(memories, f)
            print(f"Exported to JSON at {json_file}")

    def import_memory(self, okf_file: str):
        if not os.path.exists(okf_file):
            sys.exit(f"File not found: {okf_file}")
            
        print(f"Importing from {okf_file}...")
        
        # Simulate reading OKF bundle
        with open(okf_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        imported = []
        parts = content.split('<!-- okf-entry -->')
        for part in parts:
            if not part.strip():
                continue
            if part.startswith('---'):
                parts_split = part.split('---', 2)
                if len(parts_split) >= 3:
                    meta = yaml.safe_load(parts_split[1])
                    body = parts_split[2].strip()
                    imported.append({'id': meta.get('id'), 'content': body, 'type': meta.get('type')})
        return imported

def main():
    parser = argparse.ArgumentParser(description="Memory Migration CLI")
    parser.add_argument('--source', choices=['mem0', 'letta', 'supermemory'], required=True, help="Source memory system")
    subparsers = parser.add_subparsers(dest='command', required=True)

    export_parser = subparsers.add_parser('export', help='Export memories')
    export_parser.add_argument('--okf', action='store_true', help='Export to OKF bundle format')

    import_parser = subparsers.add_parser('import', help='Import memories')
    import_parser.add_argument('--file', required=True, help='OKF file to import')

    args = parser.parse_args()

    migrator = MemoryMigrator(source=args.source)

    if args.command == 'export':
        migrator.export_memory(use_okf=args.okf)
    elif args.command == 'import':
        data = migrator.import_memory(args.file)
        print("Imported Data:", data)

if __name__ == "__main__":
    main()
