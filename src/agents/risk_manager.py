def risk_manager_agent(state):
    # Edge Logic: The "Kill Switch." Overrides signals if debt is too high.
    debt = state["data"]["metrics"].get("debt_to_equity", 0)
    if debt and debt > 200:
        return {"decision": "HOLD (High Debt Risk)", "analysis_steps": ["Risk: REJECTED due to insolvency risk."]}
    return {"decision": "APPROVED", "analysis_steps": ["Risk: Portfolio constraints met."]}