from typing import TypedDict, Dict, List, Sequence, Annotated

class AgentState(TypedDict):
    # Define the agent state
    messages: Annotated[Sequence[Dict], "The messages in the conversation"]
    next: str

    def getInitialState(self) -> Dict:
        return {"messages": [], "next": "start"}
