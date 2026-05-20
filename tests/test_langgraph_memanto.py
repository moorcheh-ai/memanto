import pytest
import uuid
from pydantic import ValidationError
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpoint import MemantoCheckpointSaver, CheckpointSchema

@pytest.fixture
def sdk_client():
    return SdkClient()

@pytest.fixture
def saver(sdk_client):
    return MemantoCheckpointSaver(sdk_client=sdk_client, namespace_prefix="test_lg")

def test_checkpoint_serialization(saver):
    config = {"configurable": {"thread_id": "test_1"}}
    checkpoint = {"id": "cp1", "channel_values": {"x": 1}}
    metadata = {"source": "test"}
    
    saver.put(config, checkpoint, metadata)
    result = saver.get_tuple(config)
    
    assert result.checkpoint["id"] == "cp1"
    assert result.checkpoint["channel_values"]["x"] == 1

def test_versioned_write_increment(saver):
    config = {"configurable": {"thread_id": "test_version"}}
    checkpoint = {"id": "cp_v", "channel_values": {"v": 1}}
    metadata = {}
    
    saver.put(config, checkpoint, metadata)
    first_tuple = saver.get_tuple(config)
    
    # Simulate update
    checkpoint_update = {"id": "cp_v", "channel_values": {"v": 2}}
    saver.put(config, checkpoint_update, metadata)
    
    # Manually verify version in Memanto
    namespace = saver._get_namespace("test_version")
    record = saver.client.get_memory(namespace=namespace, key="cp_v")
    parsed = CheckpointSchema.model_validate_json(record["value"])
    assert parsed.version == 2

def test_thread_isolation(saver):
    config_1 = {"configurable": {"thread_id": "thread_1"}}
    config_2 = {"configurable": {"thread_id": "thread_2"}}
    checkpoint = {"id": "cp", "channel_values": {"val": "A"}}
    
    saver.put(config_1, checkpoint, {})
    
    assert saver.get_tuple(config_2) is None

def test_list_checkpoints(saver):
    config = {"configurable": {"thread_id": "test_list"}}
    for i in range(3):
        saver.put(config, {"id": f"cp_{i}", "channel_values": {}}, {})
    
    history = saver.list(config)
    assert len(history) == 3

def test_pydantic_validation_failure(sdk_client):
    with pytest.raises(ValidationError):
        CheckpointSchema.model_validate_json('{"invalid": "schema"}')

def test_get_latest_without_id(saver):
    config = {"configurable": {"thread_id": "latest_test"}}
    saver.put(config, {"id": "old", "channel_values": {}}, {})
    saver.put(config, {"id": "new", "channel_values": {}}, {})
    
    # No checkpoint_id provided in config
    result = saver.get_tuple(config)
    assert result.checkpoint["id"] == "new"

def test_empty_thread_returns_none(saver):
    config = {"configurable": {"thread_id": "empty_thread"}}
    assert saver.get_tuple(config) is None

def test_metadata_persistence(saver):
    config = {"configurable": {"thread_id": "meta_test"}}
    metadata = {"custom_key": "custom_val"}
    saver.put(config, {"id": "cp", "channel_values": {}}, metadata)
    
    result = saver.get_tuple(config)
    assert result.metadata["custom_key"] == "custom_val"

def test_namespace_prefixing(saver):
    config = {"configurable": {"thread_id": "prefix_test"}}
    saver.put(config, {"id": "cp", "channel_values": {}}, {})
    
    # Verify namespace starts with the prefix
    namespace = saver._get_namespace("prefix_test")
    assert namespace.startswith("test_lg")

def test_large_payload_handling(saver):
    config = {"configurable": {"thread_id": "large_test"}}
    large_val = "x" * 10000
    saver.put(config, {"id": "cp", "channel_values": {"data": large_val}}, {})
    
    result = saver.get_tuple(config)
    assert result.checkpoint["channel_values"]["data"] == large_val

def test_atomic_read_modify_write_simulation(saver):
    # Testing the internal logic of the version bump
    config = {"configurable": {"thread_id": "atomic_test"}}
    checkpoint = {"id": "sync", "channel_values": {}}
    
    saver.put(config, checkpoint, {}) # Version 1
    saver.put(config, checkpoint, {}) # Version 2
    
    record = saver.client.get_memory(saver._get_namespace("atomic_test"), "sync")
    parsed = CheckpointSchema.model_validate_json(record["value"])
    assert parsed.version == 2

def test_incorrect_checkpoint_id(saver):
    config = {"configurable": {"thread_id": "missing_id"}}
    config["configurable"]["checkpoint_id"] = "non_existent"
    assert saver.get_tuple(config) is None

def test_sdk_client_integration(sdk_client):
    # Ensure SdkClient is functioning for basic ops used by saver
    sdk_client.save_memory(namespace="test", key="k", value="v")
    assert sdk_client.get_memory(namespace="test", key="k")["value"] == "v"

def test_clear_checkpoint_namespace(saver, sdk_client):
    # Ensure no leakage between tests
    config = {"configurable": {"thread_id": "cleanup_test"}}
    saver.put(config, {"id": "cp", "channel_values": {}}, {})
    
    # simulate manual deletion
    sdk_client.delete_memory(namespace=saver._get_namespace("cleanup_test"), key="cp")
    assert saver.get_tuple(config) is None
