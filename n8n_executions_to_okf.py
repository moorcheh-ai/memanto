import json
import hashlib
import os

class N8nExecutionToOKF:
    def __init__(self, n8n_executions):
        self.n8n_executions = n8n_executions

    def convert_to_okf(self):
        okf_memories = []
        for execution in self.n8n_executions:
            # Map n8n execution to OKF memory
            memory = {
                'id': execution['id'],
                'type': 'decision',
                'source': 'n8n',
                'data': execution['data']
            }
            okf_memories.append(memory)
        return okf_memories

    def add_field_level_mapping(self, okf_memories):
        # Add field-level mapping
        for memory in okf_memories:
            memory['data'] = self.map_fields(memory['data'])
        return okf_memories

    def map_fields(self, data):
        # Implement field-level mapping
        # For example:
        if 'score' in data:
            data['score'] = self.hash_value(data['score'])
        return data

    def hash_value(self, value):
        # Hash value using SHA-256
        hashed_value = hashlib.sha256(str(value).encode()).hexdigest()
        return hashed_value

    def add_privacy_controls(self, okf_memories):
        # Implement privacy controls
        # For example:
        for memory in okf_memories:
            if 'email' in memory['data']:
                del memory['data']['email']
        return okf_memories

    def generate_okf_bundle(self):
        okf_memories = self.convert_to_okf()
        okf_memories = self.add_field_level_mapping(okf_memories)
        okf_memories = self.add_privacy_controls(okf_memories)
        okf_bundle = {
            'memories': okf_memories
        }
        return okf_bundle


# Example usage:
n8n_executions = [
    {'id': '1', 'data': {'score': '10', 'email': 'example@example.com'}},
    {'id': '2', 'data': {'score': '20', 'email': 'example2@example.com'}},
    {'id': '3', 'data': {'score': '30', 'email': 'example3@example.com'}}
]

converter = N8nExecutionToOKF(n8n_executions)
okf_bundle = converter.generate_okf_bundle()
print(json.dumps(okf_bundle, indent=4))