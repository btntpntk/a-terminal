# 1. Gemini API
# 2. Set up Input and Prompts for Investors

def fundamental_agent(state):
    metrics = state["data"]["metrics"]
    pe = metrics.get("fwd_pe", 0)
    
    # Edge Logic: Quality check. Low P/E + High ROIC = Bullish.
    signal = "BULLISH" if pe and pe < 20 else "BEARISH"
    return {
        "analysis_steps": [f"Fundamental: {signal} based on P/E of {pe}."],
        "metadata": {"fundamental_signal": signal}
    }