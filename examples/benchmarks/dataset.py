"""
Shifting Persona Dataset — "The Evolving Film Enthusiast"

5 sessions where a user's movie genre preferences evolve and contradict.
The benchmark tests whether a memory system correctly surfaces the CURRENT
preference (not stale historical data) when queried.

Each session contains messages the user sent to an AI assistant.
The golden answers define what the memory system should recall when queried.
"""

from __future__ import annotations

SESSIONS: list[dict] = [
    {
        "session_id": "session_1",
        "label": "Action-lover baseline",
        "messages": [
            "I've been really into action movies lately. Just watched John Wick and I'm obsessed.",
            "The Dark Knight is probably my all-time favourite film — Nolan's action sequences are masterclass.",
            "I want you to remember that I prefer fast-paced, high-energy films. Slow cinema bores me.",
        ],
    },
    {
        "session_id": "session_2",
        "label": "Shifting toward sci-fi",
        "messages": [
            "Actually I've been exploring sci-fi recently. Dune Part 2 completely changed my perspective.",
            "Interstellar gave me existential dread in the best way. I think sci-fi is my new favourite genre.",
            "I'm less interested in pure action now — I want films that make me think.",
        ],
    },
    {
        "session_id": "session_3",
        "label": "Documentary phase",
        "messages": [
            "I went down a documentary rabbit hole this month. Planet Earth II is stunning.",
            "I've been recommending The Social Dilemma to everyone. Non-fiction is so much richer than fiction.",
            "I now believe documentaries are more impactful than any sci-fi or action film.",
        ],
    },
    {
        "session_id": "session_4",
        "label": "Rejection of documentaries",
        "messages": [
            "Okay I lied — documentaries are too slow and preachy. I got bored after two weeks.",
            "I've gone back to something fast-paced. Watching a lot of psychological thrillers now.",
            "Gone Girl, Parasite, Knives Out — this is what I actually enjoy. Tight plots, twists.",
        ],
    },
    {
        "session_id": "session_5",
        "label": "Horror phase (current)",
        "messages": [
            "I'm currently deep in a horror kick. Hereditary is the most terrifying thing I've ever seen.",
            "Ari Aster's films feel like nothing else. Midsommar, Hereditary — I can't stop watching.",
            "Horror is my thing right now. I'm not interested in thrillers or action at the moment.",
        ],
    },
]

QUERIES: list[dict] = [
    {
        "query_id": "q1",
        "question": "What genre of movies does this user currently prefer?",
        "golden_answer": "Horror",
        "description": "Must surface the CURRENT preference (horror), not stale data",
    },
    {
        "query_id": "q2",
        "question": "What was the user's very first stated movie preference?",
        "golden_answer": "Action",
        "description": "Must recall the earliest preference (action/John Wick)",
    },
    {
        "query_id": "q3",
        "question": "Did the user ever like documentaries?",
        "golden_answer": "Yes",
        "description": "Must confirm the documentary phase happened, even though it ended",
    },
    {
        "query_id": "q4",
        "question": "Which specific film directors or films has the user mentioned?",
        "golden_answer": "John Wick, The Dark Knight, Christopher Nolan, Dune, Interstellar, Planet Earth, The Social Dilemma, Gone Girl, Parasite, Knives Out, Hereditary, Midsommar, Ari Aster",
        "description": "Tests breadth of factual recall across all sessions",
    },
    {
        "query_id": "q5",
        "question": "The user asks for a movie recommendation. What should I recommend?",
        "golden_answer": "Horror — suggest Ari Aster films, films like Hereditary or Midsommar",
        "description": "Applied current-preference test: must not recommend action/sci-fi/documentary",
    },
]
