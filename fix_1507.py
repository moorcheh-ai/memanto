```python
import logging

SUCCESSFUL_UPLOAD_STATUSES = ['success', 'ok', 'uploaded', 'uploaded successfully']

class MemoryError(Exception):
    pass

class Memory:
    def __init__(self, provenance, content):
        self.provenance = provenance
        self.content = content
        self.status = None

    def update(self, new_content, new_provenance=None, new_status=None):
        if new_status and new_status.lower() not in SUCCESSFUL_UPLOAD_STATUSES:
            raise MemoryError("Failed update")
        if new_provenance:
            self.provenance = new_provenance
        self.content = new_content
        if new_status:
            self.status = new_status

    def get_status(self):
        return self.status

def main():
    memory = Memory('validated', 'content')
    logging.info(f"Initial provenance: {memory.provenance}")
    memory.update('new_content', 'new_provenance', 'failed')
    try:
        logging.info(f"Updated provenance: {memory.provenance}")
    except MemoryError as e:
        logging.error(f"MemoryError: {e}")

if __name__ == "__main__":
    main()
```