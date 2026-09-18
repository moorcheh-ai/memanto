"""Compare answers from a real Agno agent and Memanto's live answer endpoint."""

from pathlib import Path
from typing import Any

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.ollama import Ollama

ANSWER_MODEL = "qwen2.5:1.5b"

ANSWER_CASES = [
    ("When should the weekly report be delivered?", ["Friday", "16:00", "UTC"]),
    ("What file formats should the report use?", ["Markdown", "CSV"]),
    ("What timezone does the project display?", ["Asia/Kolkata"]),
    ("What primary database does the project use?", ["PostgreSQL", "16"]),
]
INSTRUCTIONS = (
    "Answer from the stored memories in one short sentence. "
    "Keep the exact names, version numbers, time format, and timezone names "
    "used in those memories. If the answer is missing, say that it is unknown."
)


def source_answers(database: Path) -> list[dict[str, Any]]:
    agent = Agent(
        model=Ollama(
            id=ANSWER_MODEL,
            host="http://ollama:11434",
            timeout=180,
            options={"temperature": 0, "seed": 42},
        ),
        db=SqliteDb(db_file=str(database)),
        user_id="demo-user",
        add_memories_to_context=True,
        add_history_to_context=False,
        update_memory_on_run=False,
        instructions=INSTRUCTIONS,
    )
    results = []
    for question, fragments in ANSWER_CASES:
        answer = str(agent.run(question).content)
        results.append(
            {
                "question": question,
                "expected_fragments": fragments,
                "source_answer": answer,
                "source_pass": all(
                    part.casefold() in answer.casefold() for part in fragments
                ),
            }
        )
        print(f"Agno question: {question}\nAgno answer: {answer}", flush=True)
    return results


def destination_answers(
    client: Any, agent_id: str, before: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for item in before:
        response = client.answer(
            agent_id,
            item["question"],
            limit=4,
            temperature=0,
            ai_model=ANSWER_MODEL,
            header_prompt=INSTRUCTIONS,
            footer_prompt=INSTRUCTIONS,
        )
        answer = str(response.get("answer", ""))
        result = {
            **item,
            "destination_answer": answer,
            "destination_pass": all(
                part.casefold() in answer.casefold()
                for part in item["expected_fragments"]
            ),
            "destination_response": response,
        }
        results.append(result)
        print(
            f"Memanto question: {item['question']}\nMemanto answer: {answer}",
            flush=True,
        )
    return results
