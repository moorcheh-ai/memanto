from agent import app
from langchain_core.messages import HumanMessage

def run_chat():
    print("Memanto-powered LangGraph Agent (Type 'quit' to exit)")
    while True:
        user_input = input("User: ")
        if user_input.lower() == 'quit':
            break
        
        inputs = {"messages": [HumanMessage(content=user_input)]}
        for event in app.stream(inputs):
            for value in event.values():
                msg = value["messages"][-1]
                if msg.content:
                    print(f"Agent: {msg.content}")

if __name__ == "__main__":
    run_chat()
