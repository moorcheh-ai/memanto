import json
import os
import hashlib
from okf import OKF

def migrate_codex_to_okf(codex_jsonl_file, okf_file):
    okf = OKF()
    with open(codex_jsonl_file, 'r') as f:
        for line in f:
            data = json.loads(line)
            if data['type'] == 'user' or data['type'] == 'assistant':
                # Remove sensitive information
                del data['developer_instructions']
                del data['reasoning']
                del data['tool_calls']
                del data['function_payloads']
                del data['transport_state']
                # Truncate SHA-256 fingerprint
                data['source'] = hashlib.sha256(data['source'].encode()).hexdigest()[:16]
                okf.add_memory(data)
    okf.save(okf_file)

if __name__ == '__main__':
    migrate_codex_to_okf('codex_session.jsonl', 'okf_bundle.okf')