import json
from datetime import datetime
from typing import Any, Dict, List

def chatgpt_to_okf(chatgpt_export: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ChatGPT export format to OKF bundle format."""
    conversations = chatgpt_export.get('conversations', [])
    okf_bundle = {
        'metadata': {
            'format': 'OKF',
            'version': '1.0',
            'converted_from': 'ChatGPT',
            'timestamp': datetime.utcnow().isoformat(),
            'conversion_tool': 'chatgpt_to_okf_adapter'
        },
        'conversations': []
    }
    for conv in conversations:
        okf_conv = {
            'id': conv.get('id'),
            'title': conv.get('title', 'Untitled'),
            'created': conv.get('create_time'),
            'messages': []
        }
        messages = conv.get('messages', [])
        for msg in messages:
            okf_msg = {
                'role': msg.get('author', {}).get('role', 'unknown'),
                'content': msg.get('content', {}).get('parts', [''])[0],
                'timestamp': msg.get('create_time')
            }
            okf_conv['messages'].append(okf_msg)
        okf_bundle['conversations'].append(okf_conv)
    return okf_bundle
