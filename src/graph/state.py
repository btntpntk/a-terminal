from typing import Annotated, TypedDict, List
import operator

class AgentState(TypedDict):
    ticker: str
    data: dict
    analysis_steps: Annotated[List[str], operator.add]
    metadata: dict
    decision: str # BUY, SELL, HOLD