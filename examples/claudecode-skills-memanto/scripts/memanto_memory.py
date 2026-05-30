import os
import sys
import json
import argparse
import hashlib
from pathlib import Path

CONFIG_DIR = Path(".memanto")
CONFIG_FILE = CONFIG_DIR / "config.json"


def _get_api_key():
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if api_key:
        return api_key
    env_file = Path.home() / ".memanto" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("MOORCHEH_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def _get_client():
    api_key = _get_api_key()
    if not api_key:
        print("Error: MOORCHEH_API_KEY not found.")
        print("Get one free at https://moorcheh.ai, then set:")
        print("  set MOORCHEH_API_KEY=your-key-here")
        sys.exit(1)
    try:
        from memanto.cli.client.direct_client import DirectClient
        return DirectClient(api_key=api_key)
    except ImportError:
        print("Error: memanto package not installed. Run:")
        print("  pip install memanto")
        sys.exit(1)


def _load_config():
    if not CONFIG_FILE.exists():
        print("Error: not initialized. Run 'memanto init' first.")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text())


def _agent_id_for(project):
    safe = hashlib.sha256(project.encode()).hexdigest()[:12]
    return f"skill-{safe}"


def cmd_init(args):
    client = _get_client()
    project = args.project or Path.cwd().name
    agent_id = _agent_id_for(project)
    try:
        existing = client.get_agent(agent_id)
    except Exception:
        existing = None
    if not existing:
        description = f"Memanto memory for {project}"
        try:
            client.create_agent(agent_id, pattern="tool", description=description)
            print(f"✓ Created agent '{agent_id}' for project '{project}'")
        except Exception as e:
            if "already exist" not in str(e).lower():
                print(f"Warning: {e}")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"agent_id": agent_id, "project": project}, indent=2))
    print(f"✓ Memanto initialized for '{project}' (agent: {agent_id})")


def _detect_type(title, content):
    text = (title + " " + content).lower()
    if any(w in text for w in ["prefer", "like", "favorite", "dislike"]):
        return "preference"
    if any(w in text for w in ["goal", "aim", "objective", "plan to"]):
        return "goal"
    if any(w in text for w in ["decid", "chose", "selected", "opted"]):
        return "decision"
    if any(w in text for w in ["learn", "discover", "found that", "realized"]):
        return "learning"
    if any(w in text for w in ["error", "bug", "fail", "crash"]):
        return "error"
    if any(w in text for w in ["creat", "wrote", "built", "implement", "added"]):
        return "artifact"
    if any(w in text for w in ["event", "happen", "occur", "start", "finish"]):
        return "event"
    return "observation"


def cmd_remember(args):
    client = _get_client()
    config = _load_config()
    agent_id = config["agent_id"]
    memory_type = args.type or _detect_type(args.title, args.content)
    tags = list(args.tags) if args.tags else []
    if "project" in config:
        tags.append(config["project"])
    try:
        client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=args.title,
            content=args.content,
            confidence=args.confidence,
            tags=tags,
            source="tool",
        )
        print(f"✓ Stored [{memory_type}] {args.title}")
    except Exception as e:
        print(f"Error storing memory: {e}")
        sys.exit(1)


def cmd_recall(args):
    client = _get_client()
    config = _load_config()
    agent_id = config["agent_id"]
    try:
        result = client.recall(agent_id=agent_id, query=args.query, limit=args.limit)
    except Exception as e:
        print(f"Error recalling memories: {e}")
        sys.exit(1)
    memories = result.get("memories", result.get("results", []))
    if not memories:
        print("No relevant memories found.")
        return
    print(f"--- {len(memories)} relevant memory/ies ---\n")
    for m in memories:
        title = m.get("title", m.get("metadata", {}).get("title", "Untitled"))
        content = m.get("content", m.get("metadata", {}).get("content", ""))
        mtype = m.get("type", m.get("metadata", {}).get("memory_type", "?"))
        score = m.get("score", m.get("similarity", None))
        score_str = f" [score: {float(score):.3f}]" if score is not None else ""
        print(f"  [{mtype}] {title}{score_str}")
        for line in content.strip().split("\n"):
            print(f"          {line}")
        print()


def cmd_answer(args):
    client = _get_client()
    config = _load_config()
    agent_id = config["agent_id"]
    try:
        result = client.answer(agent_id=agent_id, question=args.question, limit=args.limit)
    except Exception as e:
        print(f"Error answering: {e}")
        sys.exit(1)
    answer = result.get("answer", "No answer generated.")
    sources = result.get("sources", [])
    print(f"Answer: {answer}")
    if sources:
        print(f"\n(Based on {len(sources)} memory/ies)")


def cmd_status(args):
    config = _load_config()
    agent_id = config["agent_id"]
    project = config.get("project", "?")
    client = _get_client()
    try:
        info = client.get_agent(agent_id)
        print(f"Project: {project}")
        print(f"Agent:   {agent_id}")
        print(f"Status:  active")
        ns = info.get("namespace", "")
        if ns:
            print(f"Namespace: {ns}")
    except Exception as e:
        print(f"Project: {project}")
        print(f"Agent:   {agent_id}")
        print(f"Status:  error — {e}")


def cmd_history(args):
    client = _get_client()
    config = _load_config()
    agent_id = config["agent_id"]
    kw = {}
    if args.type:
        kw["type"] = [args.type]
    try:
        result = client.recall_recent(agent_id=agent_id, limit=args.limit, **kw)
    except Exception as e:
        print(f"Error fetching history: {e}")
        sys.exit(1)
    memories = result.get("memories", result.get("results", []))
    if not memories:
        print("No memories yet.")
        return
    print(f"Recent memories ({len(memories)}):\n")
    for m in memories:
        title = m.get("title", "Untitled")
        mtype = m.get("type", m.get("metadata", {}).get("memory_type", "?"))
        created = m.get("created_at", m.get("metadata", {}).get("created_at", ""))
        print(f"  [{mtype}] {title}")
        if created:
            print(f"          {created}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Memanto Memory — cross-skill memory for developer tools"
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="Initialize memory for this project")
    p.add_argument("--project", "-p", help="Project name (default: directory name)")

    p = sub.add_parser("remember", help="Store a memory")
    p.add_argument("title", help="Title (≤100 chars)")
    p.add_argument("content", help="Memory content")
    p.add_argument("--type", "-t", help="Memory type (auto-detected if omitted)")
    p.add_argument("--tags", nargs="*", default=[], help="Tags")
    p.add_argument("--confidence", type=float, default=0.8, help="Confidence 0–1")

    p = sub.add_parser("recall", help="Search memories")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", "-l", type=int, default=5, help="Max results")

    p = sub.add_parser("answer", help="Ask based on memories (RAG)")
    p.add_argument("question", help="Your question")
    p.add_argument("--limit", "-l", type=int, default=10, help="Context memories")

    sub.add_parser("status", help="Show memory status")

    p = sub.add_parser("history", help="Show recent memories")
    p.add_argument("--limit", "-l", type=int, default=10)
    p.add_argument("--type", "-t", help="Filter by type")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "init": cmd_init,
        "remember": cmd_remember,
        "recall": cmd_recall,
        "answer": cmd_answer,
        "status": cmd_status,
        "history": cmd_history,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
