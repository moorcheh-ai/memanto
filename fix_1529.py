# 1. Extract allowed fields to a constant
ALLOWED_UPDATE_FIELDS = ['field1', 'field2', 'field3']

class MemoryRecord:
    def __init__(self, id, status, ownership, provenance, source_references):
        self.id = id
        self.status = status
        self.ownership = ownership
        self.provenance = provenance
        self.source_references = source_references
        self.field1 = None
        self.field2 = None
        self.field3 = None

    def update(self, updates):
        for key, value in updates.items():
            if key in ALLOWED_UPDATE_FIELDS:
                setattr(self, key, value)
            else:
                # 2. Align error message with downstream expectations
                raise ValueError("Unknown update field")

class MemoryRecordRepository:
    def __init__(self):
        self.records = {}
    def add_record(self, record):
        self.records[record.id] = record
    def update_record(self, id, updates):
        if id not in self.records:
            raise ValueError("Record does not exist")
        self.records[id].update(updates)

# 3. Pass repository as an argument and propagate exceptions
def update_memory(id, updates, repository):
    repository.update_record(id, updates)

if __name__ == "__main__":
    # Example usage
    repo = MemoryRecordRepository()
    repo.add_record(MemoryRecord('record_id', 'status', 'ownership', 'provenance', 'source_references'))
    update_memory('record_id', {'field1': 'new_value', 'field4': 'new_value'}, repo)
