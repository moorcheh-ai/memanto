from constants import ALLOWED_UPDATE_FIELDS

def update_memory(memory_id, updates):
    allowed_updates = {key: value for key, value in updates.items() if key in ALLOWED_UPDATE_FIELDS}
    memory = get_memory(memory_id)
    updated_memory = MemoryRecord(
        id=memory_id,
        title=allowed_updates.get("title", memory.title),
        content=allowed_updates.get("content", memory.content),
        type=allowed_updates.get("type", memory.type),
        confidence=allowed_updates.get("confidence", memory.confidence),
        tags=allowed_updates.get("tags", memory.tags),
        source=allowed_updates.get("source", memory.source),
        status=memory.status,
        actor_id=memory.actor_id,
        provenance=memory.provenance,
        source_ref=memory.source_ref,
    )
    return updated_memory