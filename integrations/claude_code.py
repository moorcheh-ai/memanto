import os
import json
from typing import Optional, Dict, Any
from memanto.integrations.base import BaseIntegration
from memanto.memory_types import MemoryType
from memanto.utils import logger

class ClaudeCodeIntegration(BaseIntegration):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.stop_hook_active = False
        self.last_assistant_message = None

    def process_stop_event(self, transcript: Dict[str, Any]) -> None:
        """
        Process the Stop event from Claude Code.

        Args:
            transcript: The transcript data from Claude Code.
        """
        if not self.stop_hook_active:
            self.stop_hook_active = True
            try:
                current_user_turn = self._get_current_user_turn(transcript)
                if current_user_turn:
                    self._distill_and_store(current_user_turn)
            finally:
                self.stop_hook_active = False

    def _get_current_user_turn(self, transcript: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract the current user turn from the transcript.

        Args:
            transcript: The transcript data from Claude Code.

        Returns:
            The current user turn if found, None otherwise.
        """
        if not transcript or 'turns' not in transcript:
            return None

        turns = transcript['turns']
        if not turns:
            return None

        # Find the last user turn before the current assistant message
        for i in range(len(turns) - 1, -1, -1):
            if turns[i]['role'] == 'user' and (i == len(turns) - 1 or turns[i + 1]['role'] == 'assistant'):
                return turns[i]

        return None

    def _distill_and_store(self, user_turn: Dict[str, Any]) -> None:
        """
        Distill and store the user turn.

        Args:
            user_turn: The user turn to distill and store.
        """
        try:
            distilled_memory = self._distill(user_turn)
            if distilled_memory:
                self.memory_store.store(distilled_memory)
        except Exception as e:
            logger.error(f"Failed to distill and store user turn: {e}")

    def _distill(self, user_turn: Dict[str, Any]) -> Optional[MemoryType]:
        """
        Distill the user turn into a memory.

        Args:
            user_turn: The user turn to distill.

        Returns:
            The distilled memory if successful, None otherwise.
        """
        try:
            # Implement distillation logic here
            # This is a placeholder for the actual distillation logic
            memory_content = user_turn.get('content', '')
            if not memory_content:
                return None

            return MemoryType(
                content=memory_content,
                metadata={
                    'source': 'claude_code',
                    'role': 'user',
                    'timestamp': user_turn.get('timestamp', '')
                }
            )
        except Exception as e:
            logger.error(f"Failed to distill user turn: {e}")
            return None