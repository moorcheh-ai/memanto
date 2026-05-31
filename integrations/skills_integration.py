"""
Memanto integration for developer skills ecosystem.
This module provides context persistence across different skill executions.
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from memanto.core.memory import Memory
from memanto.core.session import Session


@dataclass
class SkillContext:
    """Represents the context of a skill execution."""
    skill_name: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    timestamp: datetime
    session_id: str
    context_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "context_hash": self.context_hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillContext':
        return cls(
            skill_name=data["skill_name"],
            inputs=data["inputs"],
            outputs=data["outputs"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data["session_id"],
            context_hash=data["context_hash"]
        )


class SkillsMemoryIntegration:
    """
    Integration layer that provides persistent memory across developer skill executions.
    """
    
    def __init__(self, memory: Memory, session: Session):
        self.memory = memory
        self.session = session
        self.context_file = Path.home() / ".memanto" / "skills_context.json"
        self.context_file.parent.mkdir(exist_ok=True)
        
    def _hash_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> str:
        """Create a hash of the context for identification."""
        context_str = json.dumps({"inputs": inputs, "outputs": outputs}, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()
    
    def store_skill_context(
        self, 
        skill_name: str, 
        inputs: Dict[str, Any], 
        outputs: Dict[str, Any]
    ) -> str:
        """
        Store the context of a skill execution.
        
        Args:
            skill_name: Name of the skill executed
            inputs: Input parameters to the skill
            outputs: Output results from the skill
            
        Returns:
            Context hash identifier
        """
        context_hash = self._hash_context(inputs, outputs)
        timestamp = datetime.now()
        
        # Store in Memanto memory
        context_data = {
            "skill_name": skill_name,
            "inputs": inputs,
            "outputs": outputs,
            "timestamp": timestamp.isoformat(),
            "context_hash": context_hash
        }
        
        self.memory.remember(
            content=json.dumps(context_data),
            metadata={
                "skill_name": skill_name,
                "context_hash": context_hash,
                "timestamp": timestamp.isoformat(),
                "type": "skill_context"
            },
            session=self.session
        )
        
        return context_hash
    
    def recall_relevant_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recall relevant context based on a query.
        
        Args:
            query: Query to search for relevant context
            limit: Maximum number of contexts to return
            
        Returns:
            List of relevant context items
        """
        recalled = self.memory.recall(
            query=query,
            session=self.session,
            limit=limit
        )
        
        contexts = []
        for item in recalled:
            try:
                context_data = json.loads(item.content)
                contexts.append(context_data)
            except json.JSONDecodeError:
                continue
                
        return contexts
    
    def inject_context_into_prompt(self, prompt: str, query: str = None) -> str:
        """
        Inject relevant context into a prompt.
        
        Args:
            prompt: Original prompt
            query: Query to find relevant context (defaults to prompt)
            
        Returns:
            Prompt with injected context
        """
        if query is None:
            query = prompt
            
        relevant_contexts = self.recall_relevant_context(query)
        
        if not relevant_contexts:
            return prompt
            
        context_section = "\n\n# Previous Context:\n"
        for ctx in relevant_contexts:
            context_section += f"## {ctx['skill_name']} ({ctx['timestamp']})\n"
            context_section += f"Inputs: {ctx['inputs']}\n"
            context_section += f"Outputs: {ctx['outputs']}\n\n"
            
        return f"{prompt}{context_section}"