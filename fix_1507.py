```python
import re
from enum import Enum

class MemoryStatus(Enum):
    SUCCESSFUL_UPLOAD_STATUSES = ['success', 'ok', 'uploaded', 'uploaded successfully']

class Memory:
    def __init__(self, id, provenance, content):
        self.id = id
        self.provenance = provenance
        self.content = content
        self.status = None

    def update(self, new_content, new_provenance=None, new_status=None):
        if new_status and new_status.lower() not in MemoryStatus.SUCCESSFUL_UPLOAD_STATUSES:
            raise MemoryError("Failed update")
        if new_provenance:
            self.provenance = new_provenance
        self.content = new_content
        if new_status:
            self.status = new_status

def update_memory(memory, new_content, new_provenance=None, new_status=None):
    memory.update(new_content, new_provenance, new_status)
    return memory

# Example usage:
memory = Memory(1, "initial provenance", "initial content")
updated_memory = update_memory(memory, "new content", "new provenance", "success")
print(updated_memory.provenance)  # Output: new provenance
print(updated_memory.status)  # Output: success

try:
    update_memory(memory, "new content", new_status="failed")
except MemoryError as e:
    print(e)  # Output: Failed update
```