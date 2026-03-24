import asyncio
import sys
from typing import Dict, Any

from src.data.providers import fetch_all_data
from src.graph.graph import hedge_fund_app
from src.graph.state import AgentState

async def run_hedge_fund(ticker: str) -> Dict[str, Any]:
    """
    Core execution logic for the AI Hedge Fund.
    Can be called by CLI, API, or Backtester.
    """
    # 1. Ingest Data (Fundamental & Technical)
    try:
        market_data = await fetch_all_data(ticker)
    except Exception as e:
        return {"error": f"Data acquisition failed for {ticker}: {str(e)}"}

    # 2. Initialize State
    # operator.add handles the 'analysis_steps' as agents finish their nodes
    initial_state: AgentState = {
        "ticker": ticker,
        "data": market_data,
        "analysis_steps": [f"System: Starting committee analysis for {ticker}."],
        "metadata": {},
        "decision": "PENDING"
    }

    # 3. Invoke LangGraph Orchestrator
    # This triggers Fundamental -> Technical -> Sentiment -> Risk in sequence
    final_state = await hedge_fund_app.ainvoke(initial_state)

    return final_state

async def main():
    # Handle command line argument if provided, else default to AAPL
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    
    print(f"--- Executing Alpha-Stream for {ticker} ---")
    
    result = await run_hedge_fund(ticker)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    # Output the Decision and the reasoning trail
    print(f"\nFINAL DECISION: {result['decision']}")
    print("\nAGENT AUDIT TRAIL:")
    for step in result["analysis_steps"]:
        print(f"  - {step}")

if __name__ == "__main__":
    asyncio.run(main())