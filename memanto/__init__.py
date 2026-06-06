"""
Memanto - Memory that AI Agents Love!
"""
Memanto - Active Memory Companion for Developer Skills
"""

import os
from typing import Dict, List, Optional
import json
from datetime import datetime

class Memanto:
    def __init__(self, memory_file: str = ".memanto_memory.json"):
        self.memory_file = memory_file
        self.context_memory: List[Dict] = self._load_memory()
    
    def _load_memory(self) -> List[Dict]:
        """Load memory from file if exists"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_memory(self):
        """Save current memory to file"""
        with open(self.memory_file, 'w') as f:
            json.dump(self.context_memory, f, indent=2)
    
    def remember_skill_context(self, skill_name: str, input_data: str, output_data: str):
        """Store context from a skill execution"""
        context_entry = {
            "timestamp": datetime.now().isoformat(),
            "skill": skill_name,
            "input": input_data,
            "output": output_data
        }
        self.context_memory.append(context_entry)
        self._save_memory()
    
    def recall_context(self) -> str:
        """Recall all stored context as a formatted string"""
        if not self.context_memory:
            return "No previous context available."
        
        context_str = "Previous Development Context:\n"
        for entry in self.context_memory:
            context_str += f"- {entry['timestamp']}: {entry['skill']} - Input: {entry['input'][:100]}... Output: {entry['output'][:100]}...\n"
        return context_str
"""
