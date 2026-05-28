Looking at the issue description, I need to create an integration layer that allows Memanto to act as a global memory companion across different developer skill executions. The challenge is to solve "Context Fragmentation" where each terminal command is treated as isolated, and instead have Memanto actively listen to and share context between different skill executions.

Based on the repository structure, I can see this is a Python project with a `memanto` directory. I need to create an integration layer that captures the essence of the mattpocock/skills ecosystem integration with Memanto's memory system.

```diff
--- /dev/null
+++ b/integrations/skills_integration.py
@@ -1,0 +1,299 @@
+"""
+Memanto Skills Integration Layer
+
+This module provides integration between the mattpocock/skills ecosystem and Memanto's memory system,
+allowing context to persist across different skill executions.
+"""
+
+import os
+import sys
+import json
+import logging
+from datetime import datetime
+from typing import Dict, List, Optional
+import yaml
+import argparse
+
+class SkillsMemoryManager:
+    """Manages memory context across different skill executions."""
+    
+    def __init__(self, memory_file: str = ".memanto/skills_context.json"):
+        """Initialize the skills memory manager."""
+        self.memory_file = memory_file
+        self.context_data = self._load_context()
+        self.logger = logging.getLogger(__name__)
+        
+    def _load_context(self) -> Dict:
+        """Load existing context from file or create new context."""
+        try:
+            if os.path.exists(self.memory_file):
+                with open(self.memory_file, 'r') as f:
+                    return json.load(f)
+        except Exception as e:
+            self.logger.debug(f"Could not load context from {self.memory_file}: {e}")
+            pass
+            
+        return {
+            "sessions": {},
+            "developer_preferences": {},
+            "architectural_decisions": [],
+            "codebase_insights": {},
+            "skill_history": []
+        }
+        
+    def _save_context(self):
+        """Save the current context to file."""
+        try:
+            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
+            with open(self.memory_file, 'w') as f:
+                json.dump(self.context_data, f, indent=2)
+        except Exception as e:
+            self.logger.error(f"Failed to save context: {e}")
+            
+    def capture_skill_context(self, skill_name: str, context: Dict) -> None:
+        """Capture context from a skill execution."""
+        # Record the timestamp of this skill execution
+        timestamp = datetime.now().isoformat()
+        
+        # Add to skill history
+        self.context_data["skill_history"].append({
+            "skill": skill_name,
+            "timestamp": timestamp,
+            "context": context
+        })
+        
+        # Extract key architectural decisions and preferences
+        if "preferences" in context:
+            for key, value in context.get("preferences", {}).items():
+                self.context_data["developer_preferences"][key] = value
+                
+        if "architectural_notes" in context:
+            self.context_data["architectural_decisions"].extend(
+                context.get("architectural_notes", [])
+            )
+            
+        self._save_context()
+        
+    def get_contextual_memory(self) -> Dict:
+        """Get accumulated context for prompt injection."""
+        return {
+            "architectural_decisions": self.context_data.get("architectural_decisions", []),
+            "developer_preferences": self.context_data.get("developer_preferences", {}),
+            "codebase_insights": self.context_data.get("codebase_insights", {})
+        }
+        
+    def get_developer_preferences(self) -> Dict:
+        """Get developer preferences for consistent coding style."""
+        return self.context_data.get("developer_preferences", {})
+        
+    def get_architectural_decisions(self) -> List:
+        """Get architectural decisions for context."""
+        return self.context_data.get("architectural_decisions", [])
+        
+    def get_codebase_insights(self) -> Dict:
+        """Get codebase insights for context."""
+        return self.context_data.get("codebase_insights", {})
+        
+    def get_skill_history(self) -> List:
+        """Get history of skill executions."""
+        return self.context_data.get("skill_history", [])
+
+def main():
+    """Main entry point for the skills integration."""
+    parser = argparse.ArgumentParser(description="Memanto Skills Integration")
+    parser.add_argument("--skill", help="Skill name being executed")
+    parser.add_argument("--capture", action="store_true", help="Capture context from this execution")
+    parser.add_argument("--context", type=str, help="JSON context data from skill execution")
+    parser.add_argument("--output", type=str, help="Path to save context")
+    
+    args = parser.add_argument
+    
+    # Initialize context manager
+    memory_manager = SkillsMemoryManager()
+    
+    if args().capture and args.context:
+        # Capture context from current skill execution
+        try:
+            context_data = json.loads(args().context) if args().context else {}
+            memory_manager.capture_skill_context(args().skill, context_data)
+        except json.JSONDecodeError:
+            print("Invalid JSON context provided", file=sys.stderr)
+            sys.exit(1)
+            
+    # Output current context for prompt injection
+    if args().output:
+        context_to_inject = {
+            "architectural_decisions": memory_manager.get_architectural_decisions(),
+            "developer_preferences": memory_manager.get_developer_preferences(),
+            "codebase_insights": memory_manager.get_codebase_insights()
+        }
+        
+        try:
+            with open(args().output, 'w') as f:
+                json.dump(context_to_inject, f, indent=2)
+        except Exception as e:
+            print(f"Error writing to output file: {e}", file=sys.stderr)
+            sys.exit(1)
+    
+    # Print usage information
+    if args().skill:
+        print(f"Context captured from skill: {args().skill}")
+        print("Current contextual memory:")
+        print(json.dumps(memory_manager.get_contextual_memory(), indent=2))
+    else:
+        print("Skills Integration Manager Active")
+        print("Usage: memanto-skills [options]")
+        print("  --skill SKILL_NAME    Name of the skill being executed")
+        print("  --context CONTEXT       JSON context from skill")
+        print("  --capture              Capture context from this execution")
+        print("  --output FILE          Output file for context")
+        print()
+        print("Examples:")
+        print("  memanto-skills --skill /gr