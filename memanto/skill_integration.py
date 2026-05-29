"""
Memanto Skill Integration - Enables Memanto to act as a global memory companion
across different developer skill executions by capturing and sharing context.
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib

class MemantoSkillIntegration:
    """Integration layer for Memanto to work with developer skills as a memory companion."""
    
    def __init__(self, memory_backend=None):
        """Initialize the Memanto skill integration system."""
        self.context_memory = {}  # In-memory storage for session context
        self.skill_history = []  # Store history of skill executions
        self.memory_backend = memory_backend
        self.current_session_context = {}
        
    def capture_skill_context(self, skill_name: str, skill_output: str, skill_input: str = None):
        """Capture context from a skill execution."""
        context_entry = {
            'skill': skill_name,
            'timestamp': datetime.utcnow().isoformat(),
            'input': skill_input,
            'output': skill_output,
            'hash': self._hash_content(skill_input + skill_output) if skill_input else self._hash_content(skill_output)
        }
        self.skill_history.append(context_entry)
        return context_entry
        
    def _hash_content(self, content: str) -> str:
        """Create a hash of content for identification."""
        return hashlib.md5(content.encode()).hexdigest()
        
    def store_context(self, key: str, context_data: Dict[str, Any]):
        """Store context data in memory."""
        self.context_memory[key] = {
            'data': context_data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    def retrieve_context(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored context by key."""
        return self.context_memory.get(key)
        
    def get_skill_context(self) -> Dict[str, Any]:
        """Get the current skill context for injection into prompts."""
        return {
            'architectural_decisions': self._get_stored_architectural_decisions(),
            'codebase_quirks': self._get_stored_codebase_quirks(),
            'coding_preferences': self._get_stored_coding_preferences(),
            'recent_skill_executions': self.skill_history[-10:] if self.skill_history else []  # Last 10 executions
        }
        
    def _get_stored_architectural_decisions(self) -> List[Dict]:
        """Retrieve architectural decisions from memory."""
        # This would typically query a persistent store
        # For now, return from in-memory context
        return []
        
    def _get_stored_codebase_quirks(self) -> List[Dict]:
        """Retrieve stored codebase quirks."""
        # This would typically query a persistent store
        return []
        
    def _get_stored_coding_preferences(self) -> Dict:
        """Retrieve coding preferences."""
        # This would typically query a persistent store
        return {}
        
    def inject_context_to_prompt(self, prompt: str) -> str:
        """Inject relevant context into a prompt."""
        context = self.get_skill_context()
        if not context:
            return prompt
            
        # Add context to prompt
        context_prompt = "\n\n[Context Information]\n"
        context_prompt += "Previous architectural decisions:\n"
        for decision in context.get('architectural_decisions', []):
            context_prompt += f"- {decision}\n"
            
        context_prompt += "\nCodebase quirks observed:\n"
        for quirk in context.get('codebase_quirks', []):
            context_prompt += f"- {quirk}\n"
            
        context_prompt += "\nDeveloper preferences:\n"
        for preference in context.get('coding_preferences', []):
            context_prompt += f"- {preference}\n"
            
        return prompt + context_prompt
        
    def remember_skill_execution(self, skill_name: str, skill_input: str, skill_output: str):
        """Remember a skill execution for context preservation."""
        # Capture the skill execution context
        context_data = {
            'skill_name': skill_name,
            'executed_at': datetime.utcnow().isoformat(),
            'input': skill_input,
            'output': skill_output
        }
        
        # Store this execution in history
        self.capture_skill_context(skill_name, skill_output, skill_input)
        return context_data
        
    def get_developer_context_profile(self) -> Dict[str, Any]:
        """Get developer's coding profile from stored context."""
        return {
            'architectural_decisions': self._get_stored_architectural_decisions(),
            'codebase_quirks': self._get_stored_codebase_quirks(),
            'coding_preferences': self._get_stored_coding_preferences()
        }

# Usage example:
# skill_integration = MemantoSkillIntegration()
# skill_integration.remember_skill_execution("grill-with-docs", "user input", "skill output")
# Context is now stored and can be injected into future skill executions