import logging
from memanto.app.constants import ALLOWED_UPDATE_FIELDS

logging.basicConfig(level=logging.INFO)

def update_memory(memory_id, namespace, updates):
    """
    Updates an existing memory record, restricting changes to ALLOWED_UPDATE_FIELDS.
    """
    # 1. Align with get_memory contract and handle missing records
    memory = get_memory(memory_id, namespace)
    if memory is None:
        raise ValueError(f"Memory record {memory_id} not found in namespace {namespace}")

    # 2. Log fields removed by the whitelist (names only, not values)
    dropped_fields = [k for k in updates if k not in ALLOWED_UPDATE_FIELDS]
    if dropped_fields:
        logging.warning(f"Update dropped protected fields: {', '.join(dropped_fields)}")

    # 3. Filter updates
    allowed_updates = {k: v for k, v in updates.items() if k in ALLOWED_UPDATE_FIELDS}

    # 4. Reconstruct the complete MemoryRecord, not a partial record
    # Normalize the existing record to a dictionary to preserve all fields (agent_id, created_at, etc.)
    if hasattr(memory, 'model_dump'):  # Pydantic v2
        existing_data = memory.model_dump()
    elif hasattr(memory, 'dict'):      # Pydantic v1
        existing_data = memory.dict()
    else:                               # Standard object
        existing_data = vars(memory).copy()

    # Overlay only allowed updates
    existing_data.update(allowed_updates)

    # Return the reconstructed record
    return MemoryRecord(**existing_data)
