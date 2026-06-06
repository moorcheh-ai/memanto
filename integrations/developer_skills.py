"""
Integration layer for developer skills with Memanto context memory
"""

import subprocess
import sys
from typing import List, Optional
import os

# Import Memanto
try:
    from memanto import Memanto
except ImportError:
    # Fallback if not installed
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from memanto import Memanto

class SkillWithMemory:
    def __init__(self):
        self.memanto = Memanto()
    
    def execute_skill(self, skill_command: str, args: List[str], input_data: str = "") -> str:
        """
        Execute a developer skill with memory integration
        """
        # Add previous context to the input
        context = self.memanto.recall_context()
        enhanced_input = f"{context}\n\nCurrent Task:\n{input_data}"
        
        # Execute the skill command
        try:
            result = subprocess.run(
                [skill_command] + args,
                input=enhanced_input,
                text=True,
                capture_output=True,
                timeout=300  # 5 minute timeout
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            output = "Skill execution timed out"
        except Exception as e:
            output = f"Error executing skill: {str(e)}"
        
        # Store the context for future skills
        self.memanto.remember_skill_context(
            skill_name=skill_command,
            input_data=input_data,
            output_data=output
        )
        
        return output

def main():
    """Main entry point for the Memanto-enhanced skills"""
    if len(sys.argv) < 2:
        print("Usage: memanto-skills <skill_command> [args...]")
        sys.exit(1)
    
    skill_cmd = sys.argv[1]
    skill_args = sys.argv[2:] if len(sys.argv) > 2 else []
    
    # Read input from stdin if available
    if not sys.stdin.isatty():
        input_data = sys.stdin.read()
    else:
        input_data = ""
    
    skill_executor = SkillWithMemory()
    result = skill_executor.execute_skill(skill_cmd, skill_args, input_data)
    
    print(result)

if __name__ == "__main__":
    main()