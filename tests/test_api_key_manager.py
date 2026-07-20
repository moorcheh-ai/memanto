import unittest
from memanto.api_key_manager import _normalize_duplicated_api_key

class TestAPIKeyManager(unittest.TestCase):
    def test_normalize_duplicated_api_key(self):
        # Arrange
        duplicated_key = "ab" * 32
        
        # Act
        normalized_key = _normalize_duplicated_api_key(duplicated_key)
        
        # Assert
        self.assertEqual(normalized_key, duplicated_key)

    def test_normalize_duplicated_api_key_short(self):
        # Arrange
        short_key = "ab" * 16
        
        # Act
        normalized_key = _normalize_duplicated_api_key(short_key)
        
        # Assert
        self.assertEqual(normalized_key, short_key)