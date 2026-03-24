from langgraph.graph import StateGraph, END
from src.agents.fundamental_agent import fundamental_agent
from src.agents.risk_manager import risk_manager_agent
from src.graph.state import AgentState

builder = StateGraph(AgentState)
builder.add_node("fundamental", fundamental_agent)
builder.add_node("risk", risk_manager_agent)

builder.set_entry_point("fundamental")
builder.add_edge("fundamental", "risk")
builder.add_edge("risk", END)

hedge_fund_app = builder.compile()