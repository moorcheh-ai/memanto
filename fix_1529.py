class MemoryRecord:
    def __init__(self, id, status, ownership, provenance, source_references, **kwargs):
        self.id = id
        self.status = status
        self.ownership = ownership
        self.provenance = provenance
        self.source_references = source_references
        for key, value in kwargs.items():
            setattr(self, key, value)

    def update(self, updates):
        allowed_update_fields = ['field1', 'field2', 'field3']  # define allowed fields
        for key, value in updates.items():
            if key in allowed_update_fields:
                setattr(self, key, value)
            else:
                raise ValueError(f"Updating field '{key}' is not allowed")

class MemoryRecordRepository:
    def __init__(self):
        self.records = {}

    def get_record(self, id):
        return self.records.get(id)

    def update_record(self, id, updates):
        record = self.get_record(id)
        if record:
            record.update(updates)
        else:
            raise ValueError(f"Record with id '{id}' does not exist")

    def add_record(self, record):
        self.records[record.id] = record

def update_memory(id, updates):
    repository = MemoryRecordRepository()
    repository.add_record(MemoryRecord(id, 'status', 'ownership', 'provenance', 'source_references'))
    try:
        repository.update_record(id, updates)
    except ValueError as e:
        print(e)

update_memory('record_id', {'field1': 'new_value', 'field4': 'new_value'})