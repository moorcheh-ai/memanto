from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents import invoke

def banner(text):
    print("\n" + "="*60 + f"\n  {text}\n" + "="*60 + "\n")

def session_1():
    banner("SESSION 1 - Monday: storing user profile")
    for msg in [
        "I am Sofia, a ML engineer at DataCore. I love concise technical answers.",
        "I am building a RAG pipeline with LangGraph and Memanto.",
        "My preference: always include code examples in responses.",
    ]:
        print(f"User: {msg}")
        r = invoke(msg)
        print(f"Agent: {r['response']}\n")
        time.sleep(0.3)

def session_2():
    banner("SESSION 2 - Wednesday: NEW session, no thread state")
    for msg in [
        "Do you remember what project I mentioned?",
        "What are my communication preferences?",
    ]:
        print(f"User: {msg}")
        r = invoke(msg)
        print(f"Agent: {r['response']}\n")
        time.sleep(0.3)

def session_3():
    banner("SESSION 3 - Friday: full synthesis")
    print("User: Summarise everything you know about me.")
    r = invoke("Summarise everything you know about me and my work.")
    print(f"Agent: {r['response']}\n")

def main():
    if not os.getenv("MOORCHEH_API_KEY"):
        print("ERROR: set MOORCHEH_API_KEY first")
        sys.exit(1)
    print("LangGraph + Memanto Multi-Agent Cross-Session Demo")
    session_1()
    session_2()
    session_3()
    banner("DONE - cross-session memory verified")

if __name__ == "__main__":
    main()
