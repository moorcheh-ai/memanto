import pytest
from memanto.client import DirectClient, SdkClient
from memanto.types import InputLimits

class TestClientValidation:
    @pytest.fixture
    def direct_client(self):
        return DirectClient()

    @pytest.fixture
    def sdk_client(self):
        return SdkClient()

    def test_validate_query_empty(self, direct_client, sdk_client):
        with pytest.raises(ValueError, match="Query cannot be empty or blank."):
            direct_client._validate_query("")
        with pytest.raises(ValueError, match="Query cannot be empty or blank."):
            sdk_client._validate_query("")

    def test_validate_query_too_long(self, direct_client, sdk_client):
        long_query = "a" * (InputLimits.MAX_QUERY_LENGTH + 1)
        with pytest.raises(ValueError, match=f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters."):
            direct_client._validate_query(long_query)
        with pytest.raises(ValueError, match=f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters."):
            sdk_client._validate_query(long_query)

    def test_validate_query_invalid_limit(self, direct_client, sdk_client):
        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            direct_client._validate_query("valid query", 0)
        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            sdk_client._validate_query("valid query", InputLimits.MAX_RECALL_LIMIT + 1)
        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            direct_client._validate_query("valid query", "10")
        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            sdk_client._validate_query("valid query", 1.5)

    def test_answer_validation(self, direct_client, sdk_client):
        # Test valid answer call
        direct_client.answer("valid question", 5)
        sdk_client.answer("valid question", 5)

        # Test invalid answer calls
        with pytest.raises(ValueError, match="Query cannot be empty or blank."):
            direct_client.answer("", 5)
        with pytest.raises(ValueError, match="Query cannot be empty or blank."):
            sdk_client.answer("", 5)

        long_question = "a" * (InputLimits.MAX_QUERY_LENGTH + 1)
        with pytest.raises(ValueError, match=f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters."):
            direct_client.answer(long_question, 5)
        with pytest.raises(ValueError, match=f"Query exceeds maximum length of {InputLimits.MAX_QUERY_LENGTH} characters."):
            sdk_client.answer(long_question, 5)

        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            direct_client.answer("valid question", 0)
        with pytest.raises(ValueError, match=f"Limit must be an integer between 1 and {InputLimits.MAX_RECALL_LIMIT}."):
            sdk_client.answer("valid question", InputLimits.MAX_RECALL_LIMIT + 1)