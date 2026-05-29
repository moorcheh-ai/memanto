"""
Developer Skills Integration for Memanto

This module provides an integration layer that allows Memanto to act as a 
global memory companion across different developer skill executions.
"""

import os
import json
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path
from memanto import Memanto


class DeveloperSkillsIntegration:
    """Integration layer for developer skills with Memanto memory persistence."""
    
    def __init__(self, memanto: Memanto, context_file: str = ".memanto_context.json"):
        """
        Initialize the integration.
        
        Args:
            memanto: Memanto instance for memory operations
            context_file: File to store current context state
        """
        self.memanto = memanto
        self.context_file = context_file
        self.session_id = self._get_session_id()
        
    def _get_session_id(self) -> str:
        """Generate a unique session ID based on timestamp and process."""
        import time
        import hashlib
        session_data = f"{time.time()}_{os.getpid()}"
        return hashlib.md5(session_data.encode()).hexdigest()[:12]
    
    def capture_skill_execution(
        self, 
        skill_name: str, 
        inputs: Dict[str, Any], 
        outputs: Dict[str, Any]
    ) -> None:
        """
        Capture the execution of a developer skill.
        
        Args:
            skill_name: Name of the skill executed
            inputs: Input parameters to the skill
            outputs: Output results from the skill
        """
        # Create context entry
        context_entry = {
            "skill_name": skill_name,
            "session_id": self.session_id,
            "timestamp": self._get_timestamp(),
            "inputs": inputs,
            "outputs": outputs
        }
        
        # Store in Memanto memory
        self.memanto.remember(
            f"skill_execution_{skill_name}_{self.session_id}",
            json.dumps(context_entry, indent=2)
        )
        
        # Save to local context file for immediate access
        self._save_local_context(context_entry)
        
        # Extract and store architectural decisions and patterns
        self._extract_architectural_context(context_entry)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
        
    def _save_local_context(self, context: Dict[str, Any]) -> None:
        """Save context to local file for immediate access."""
        try:
            with open(self.context_file, 'w') as f:
                json.dump(context, f, indent=2)
        except Exception:
            pass  # Fail silently to not interrupt workflow
            
    def _extract_architectural_context(self, context_entry: Dict[str, Any]) -> None:
        """
        Extract architectural decisions and coding patterns from skill execution.
        
        Args:
            context_entry: The full context entry to analyze
        """
        # Extract key information that represents architectural choices
        architectural_context = {
            "timestamp": context_entry["timestamp"],
            "skill_name": context_entry["skill_name"],
            "decisions": self._extract_decisions(context_entry),
            "patterns": self._extract_patterns(context_entry),
            "preferences": self._extract_preferences(context_entry)
        }
        
        # Store architectural context separately for easy retrieval
        self.memanto.remember(
            f"architectural_context_{context_entry['skill_name']}_{self.session_id}",
            json.dumps(architectural_context, indent=2)
        )
        
    def _extract_decisions(self, context_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract architectural decisions from context."""
        # This would be enhanced with LLM analysis in a real implementation
        decisions = {}
        if 'outputs' in context_entry:
            # Look for decision-making keywords in outputs
            output_str = str(context_entry['outputs']).lower()
            if 'architecture' in output_str or 'design' in output_str:
                decisions['design_choices'] = "Identified architectural decisions in outputs"
        return decisions
        
    def _extract_patterns(self, context_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract coding patterns from context."""
        # Placeholder for pattern extraction logic
        return {"coding_style": "default"}
        
    def _extract_preferences(self, context_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract developer preferences from context."""
        # Placeholder for preference extraction logic
        return {"preferences": "default"}
        
    def get_context_for_skill(self, skill_name: str) -> Dict[str, Any]:
        """
        Retrieve relevant context for a specific skill.
        
        Args:
            skill_name: Name of the skill to get context for
            
        Returns:
            Dictionary containing relevant context
        """
        # Try to get recent context first
        try:
            with open(self.context_file, 'r') as f:
                local_context = json.load(f)
                return local_context
        except FileNotFoundError:
            pass
        except Exception:
            pass
            
        # Fall back to Memanto memory
        try:
            memories = self.memanto.recall(f"skill_execution_{skill_name}")
            if memories:
                # Return most recent memory
                return json.loads(memories[0])
        except Exception:
            pass
            
        return {}