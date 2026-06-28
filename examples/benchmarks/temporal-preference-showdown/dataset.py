"""
Temporal Preference Drift Dataset
==================================
A personal assistant agent scenario where user preferences and facts evolve
across 5 distinct sessions. Each session adds new or contradicting information.

This tests the core challenge of agentic memory in 2026:
  - Does the system remember WHAT happened AND WHEN?
  - When preferences change, does the system surface the CURRENT state?
  - Does stale data pollute the active context?
"""

SESSIONS = [
    {
        "id": "session_1",
        "label": "Initial onboarding",
        "messages": [
            {"role": "user", "content": "Hi! I'm Alex, a backend developer at a startup in London."},
            {"role": "assistant", "content": "Nice to meet you, Alex! What brings you here?"},
            {"role": "user", "content": "I mainly work with Python and Django. I prefer dark mode in all my tools."},
            {"role": "assistant", "content": "Got it — Python/Django developer, dark mode fan."},
            {"role": "user", "content": "I'm vegetarian and I like to keep meetings under 30 minutes."},
            {"role": "assistant", "content": "Noted! Short meetings and plant-based diet."},
        ],
    },
    {
        "id": "session_2",
        "label": "Tech stack shift",
        "messages": [
            {"role": "user", "content": "We just migrated our entire backend to Go. I've been learning it for 3 months."},
            {"role": "assistant", "content": "That's a significant change! How are you finding Go?"},
            {"role": "user", "content": "It's great for performance. I think I prefer Go over Python now for backend work."},
            {"role": "assistant", "content": "Understood — Go is now your preferred backend language."},
            {"role": "user", "content": "Also I moved to Berlin last month. London was too expensive."},
            {"role": "assistant", "content": "Berlin is a great city for tech! I'll note your new location."},
        ],
    },
    {
        "id": "session_3",
        "label": "Role promotion",
        "messages": [
            {"role": "user", "content": "I just got promoted to Senior Engineer. Managing 2 junior devs now."},
            {"role": "assistant", "content": "Congratulations on the promotion!"},
            {"role": "user", "content": "Actually I've been reconsidering Go. For our new AI services we're back to Python — specifically FastAPI and async."},
            {"role": "assistant", "content": "So Python with FastAPI for AI services, Go for the existing backend?"},
            {"role": "user", "content": "Exactly. Python with FastAPI is my main focus now."},
            {"role": "assistant", "content": "Got it — Python/FastAPI as primary, Go secondary."},
        ],
    },
    {
        "id": "session_4",
        "label": "Diet and health update",
        "messages": [
            {"role": "user", "content": "I started eating fish again. I'm pescatarian now, not strictly vegetarian."},
            {"role": "assistant", "content": "Thanks for the update — pescatarian diet noted."},
            {"role": "user", "content": "Also I prefer voice calls over Slack messages for async work. Slack is too noisy."},
            {"role": "assistant", "content": "Voice calls over Slack for async communication — noted."},
        ],
    },
    {
        "id": "session_5",
        "label": "Leadership expansion",
        "messages": [
            {"role": "user", "content": "Big news — I'm now the Engineering Lead. Team grew to 8 people."},
            {"role": "assistant", "content": "Wow, from Senior Engineer to Engineering Lead with a team of 8!"},
            {"role": "user", "content": "We standardized on Python across the whole company. Dropped Go entirely."},
            {"role": "assistant", "content": "Full Python standardization — that simplifies things."},
            {"role": "user", "content": "I also switched to light mode. Turns out dark mode was giving me headaches."},
            {"role": "assistant", "content": "Switched to light mode — comfort over aesthetics!"},
        ],
    },
]

# Golden evaluation queries: (query, correct_answer_keywords, stale_answer_keywords)
# correct_answer_keywords = what the CORRECT (most recent) answer should contain
# stale_answer_keywords = what a WRONG (stale/outdated) answer would say
QUERIES = [
    {
        "id": "q1",
        "query": "What programming language does Alex prefer for backend development?",
        "correct_keywords": ["python"],
        "stale_keywords": ["go", "golang", "django"],
        "explanation": "Evolved: Python → Go → Python/FastAPI → Python (company-wide)",
    },
    {
        "id": "q2",
        "query": "Where does Alex live?",
        "correct_keywords": ["berlin"],
        "stale_keywords": ["london"],
        "explanation": "Moved from London to Berlin in session 2",
    },
    {
        "id": "q3",
        "query": "What is Alex's current role and team size?",
        "correct_keywords": ["engineering lead", "8", "lead"],
        "stale_keywords": ["senior", "junior", "2 devs", "two"],
        "explanation": "Promoted: Backend dev → Senior Engineer → Engineering Lead (8 people)",
    },
    {
        "id": "q4",
        "query": "What is Alex's diet?",
        "correct_keywords": ["pescatarian", "fish"],
        "stale_keywords": ["vegetarian", "vegan", "plant"],
        "explanation": "Changed from vegetarian to pescatarian in session 4",
    },
    {
        "id": "q5",
        "query": "Does Alex prefer dark mode or light mode?",
        "correct_keywords": ["light", "light mode"],
        "stale_keywords": ["dark", "dark mode"],
        "explanation": "Switched from dark to light mode in session 5 due to headaches",
    },
    {
        "id": "q6",
        "query": "How does Alex prefer to communicate asynchronously?",
        "correct_keywords": ["voice", "call", "voice call"],
        "stale_keywords": ["slack", "message"],
        "explanation": "Switched from Slack to voice calls in session 4",
    },
]

USER_ID = "alex_benchmark_2026"
