"""
Memanto Skills Integration Module

This module provides integration between Memanto and the mattpocock/skills ecosystem,
allowing Memanto to act as an active memory companion across different skill executions.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

class SkillsIntegration:
    """
    Integration layer for Memanto to work with developer skills ecosystem
    """
    
    def __init__(self, db_path: str = "memanto_skills.db"):
        self.db_path = db_path
        self.context_db = None
        self._init_database()
    
    def _init_database(self):
        """Initialize the skills context database"""
        self.context_db = sqlite3.connect(self.db_path)
        self.context_db.execute('''
            CREATE TABLE IF NOT EXISTS skill_contexts (
                id INTEGER PRIMARY KEY,
                session_id TEXT UNIQUE,
                skill_name TEXT,
                context_data TEXT,
                timestamp DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.context_db.commit()
    
    def store_skill_context(self, session_id: str, skill_name: str, context_data: Dict[str, Any]) -> bool:
        """
        Store skill context for later retrieval
        
        Args:
            session_id: Unique identifier for the skill session
            skill_name: Name of the skill being executed
            context_data: Context data to store
            
        Returns:
            bool: Success status
        """
        try:
            cursor = self.context_db.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO skill_contexts 
                (session_id, skill_name, context_data, timestamp) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (session_id, skill_name, json.dumps(context_data)))
            self.context_db.commit()
            return True
        except Exception as e:
            print(f"Error storing skill context: {e}")
            return False
    
    def retrieve_skill_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve stored skill context
        
        Args:
            session_id: Session identifier to retrieve context for
            
        Returns:
            Dict containing context data or None
        """
        try:
            cursor = self.context_db.cursor()
            cursor.execute('''
                SELECT context_data FROM skill_contexts 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (session_id,))
            result = cursor.fetchone()
            if result:
                return json.loads(result[0]) if result[0] else None
            return None
        except Exception as e:
            print(f"Error retrieving skill context: {e}")
            return None
    
    def enrich_skill_prompt(self, base_prompt: str, skill_context: Dict[str, Any] = None) -> str:
        """
        Enrich a skill prompt with relevant context
        
        Args:
            base_prompt: The original prompt
            skill_context: Optional existing context to include
            
        Returns:
            Enhanced prompt with context
        """
        if not skill_context:
            return base_prompt
        
        # Extract relevant architectural decisions and preferences from context
        context_items = []
        if 'architecture_decisions' in skill_context:
            context_items.append(f"Architecture Decisions: {skill_context['architecture_decisions']}")
        if 'coding_preferences' in skill_context:
            context_items.append(f"Coding Preferences: {skill_context['coding_preferences']}")
        if 'codebase_quirks' in skill_context:
            context_items.append(f"Codebase Quirks: {skill_context['codebase_quirks']}")
        
        if context_items:
            context_str = "Context Information:\n" + "\n".join(context_items)
            return f"{context_str}\n\n{base_prompt}"
        
        return base_prompt
    
    def record_skill_execution(self, skill_name: str, inputs: str, outputs: str):
        """
        Record a skill execution with its inputs and outputs
        
        Args:
            skill_name: Name of the skill executed
            inputs: Input data for the skill
            outputs: Output data from the skill
        """
        context_data = {
            'skill_name': skill_name,
            'inputs': inputs,
            'outputs': outputs,
            'timestamp': datetime.now().isoformat()
        }
        
        # Store this execution for context continuity
        self.store_skill_context(
            session_id=f"skill_{skill_name}_{datetime.now().timestamp()}",
            skill_name=skill_name,
            context_data=context_data
        )