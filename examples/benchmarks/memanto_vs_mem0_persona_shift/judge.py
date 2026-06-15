import os
import json
from groq import Groq

class LLMJudge:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"  # Using Groq's fast Llama 3 model

    def evaluate(self, expected_state: str, retrieved_context: str) -> dict:
        """
        Evaluates the retrieved_context against the expected_state.
        Returns a dict with 'score' (0-100) and 'reasoning'.
        """
        prompt = f"""
        You are an expert AI evaluator judging the accuracy of a memory retrieval system.
        
        The user has a dynamically shifting persona and preferences over time.
        
        EXPECTED CURRENT STATE:
        {expected_state}
        
        RETRIEVED CONTEXT FROM MEMORY SYSTEM:
        {retrieved_context}
        
        Your task is to grade how accurately the RETRIEVED CONTEXT captures the EXPECTED CURRENT STATE.
        A perfect score means the retrieved context clearly highlights the current preferences and downplays or correctly contextualizes outdated preferences.
        A low score means the retrieved context is bloated with contradictory outdated information or misses the current state entirely.
        
        Output your evaluation in strict JSON format:
        {{
            "score": <int between 0 and 100>,
            "reasoning": "<brief explanation of the score>"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a JSON-outputting evaluator. Output only valid JSON without markdown wrapping."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.0
            )
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            return {"score": 0, "reasoning": f"Judge failed: {str(e)}"}
