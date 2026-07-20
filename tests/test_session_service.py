import unittest
from memanto.session_service import SessionService
from memanto.utils import validate_safe_id

class TestSessionService(unittest.TestCase):
    def test_delete_session_rejects_unsafe_agent_id(self):
        # Arrange
        service = SessionService()
        unsafe_agent_id = "../etc/passwd"
        
        # Act and Assert
        with self.assertRaises(ValueError):
            service.delete_session(unsafe_agent_id)

    def test_delete_session_accepts_safe_agent_id(self):
        # Arrange
        service = SessionService()
        safe_agent_id = "safe_agent"
        
        # Act
        service.delete_session(safe_agent_id)
        
        # Assert
        # Add appropriate assertions based on the session deletion logic
        pass