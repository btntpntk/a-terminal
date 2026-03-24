import operator
from typing import Annotated, Dict, List, TypedDict, Any


class AgentState(TypedDict):
    """
    Represents the shared state of the agent graph.
    """
    ticker: str
    data_payload: Dict[str, Any]
    # The audit log accumulates messages from each agent step
    audit_log: Annotated[List[str], operator.add]
    # Agent-specific outputs
    fundamental_analysis: str
    technical_analysis: str
    sentiment_analysis: str
    risk_assessment: str
    final_decision: str