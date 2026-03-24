import asyncio
import questionary
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.layout import Layout

# Import your core logic and calculators
from src.data.providers import fetch_all_data
from src.graph.graph import hedge_fund_app
from src.agents.calculator import (
    calculate_sloan_ratio, calculate_cvar_95, calculate_wacc, 
    calculate_roic, calculate_rolling_sortino, calculate_asset_turnover,
    calculate_altman_z, calculate_ccc, generate_alpha_score
)

console = Console()

def create_metric_card(title: str, value: any, color: str = "white") -> Panel:
    """Helper to create small, scannable KPI cards."""
    formatted_val = f"{value:.4f}" if isinstance(value, float) else str(value)
    return Panel(f"[bold {color}]{formatted_val}[/bold {color}]", title=title, expand=False)

async def run_analysis_cli():
    console.print(Panel.fit("[bold green]ALPHA-STREAM ARCHITECT: QUANTITATIVE TERMINAL[/bold green]", border_style="green"))
    
    ticker = await questionary.text("Enter Ticker (e.g., CPALL.BK):").ask_async()
    if not ticker: return

    with console.status(f"[bold yellow]Running Institutional Suite for {ticker}...", spinner="bouncingBar"):
        # 1. Fetch Raw Data via Provider
        market_data = await fetch_all_data(ticker)
        stock = market_data['raw_stock_obj'] # Assuming provider returns yf object
        returns = market_data['returns']
        
        # 2. Execute Local Calculations
        # These provide the data-driven foundation for the agents
        s_ratio = calculate_sloan_ratio(stock.financials, stock.cashflow, stock.balance_sheet)
        wacc = calculate_wacc(stock.info, stock.financials, stock.balance_sheet, stock.cashflow)
        roic = calculate_roic(stock.financials, stock.balance_sheet)
        cvar = calculate_cvar_95(returns)
        sortino = calculate_rolling_sortino(returns)
        a_turnover = calculate_asset_turnover(stock.financials, stock.balance_sheet)
        z_score = calculate_altman_z(stock.financials, stock.balance_sheet)
        ccc_val = calculate_ccc(stock.financials, stock.balance_sheet)
        
        alpha = generate_alpha_score(roic, wacc, s_ratio, z_score, sortino, 0)

        # 3. Run Multi-Agent Graph for Qualitative Consensus
        result = await hedge_fund_app.ainvoke({
            "ticker": ticker,
            "data": market_data,
            "analysis_steps": [],
            "metadata": {"alpha_score": alpha}
        })

    # --- RENDERING THE DASHBOARD ---

    # Row 1: The "Moat" & Alpha Layer
    moat_spread = roic - wacc
    spread_color = "green" if moat_spread > 0 else "red"
    
    moat_row = Columns([
        create_metric_card("ROIC", roic, "cyan"),
        create_metric_card("WACC", wacc, "yellow"),
        create_metric_card("Moat Spread", moat_spread, spread_color),
        create_metric_card("ALPHA SCORE", alpha, "bold magenta")
    ])
    
    # Row 2: Risk & Quality Layer
    quality_row = Columns([
        create_metric_card("Sloan Ratio", s_ratio, "white" if s_ratio < 0.1 else "red"),
        create_metric_card("Altman Z-Score", z_score, "green" if z_score > 2.9 else "red"),
        create_metric_card("CVaR (95%)", cvar, "red"),
        create_metric_card("Sortino", sortino, "green" if sortino > 1 else "yellow")
    ])

    # Row 3: Operational Efficiency
    efficiency_row = Columns([
        create_metric_card("Asset Turnover", a_turnover, "blue"),
        create_metric_card("Cash Conv. Cycle", ccc_val, "blue")
    ])

    console.print("\n[bold]1. FUNDAMENTAL & QUANTITATIVE INTELLIGENCE[/bold]")
    console.print(moat_row)
    console.print(quality_row)
    console.print(efficiency_row)

    # Agent Audit Table
    table = Table(title="\n[bold]2. COMMITTEE REASONING LOG[/bold]", title_justify="left", box=None)
    table.add_column("Agent", style="bold cyan", width=15)
    table.add_column("Audit Trail", style="italic white")

    for step in result["analysis_steps"]:
        if ":" in step:
            agent, reason = step.split(":", 1)
            table.add_row(agent.strip(), reason.strip())
        else:
            table.add_row("System", step)

    console.print(table)
    
    # Final Verdict
    decision_color = "green" if "BUY" in result['decision'] else "red" if "SELL" in result['decision'] else "yellow"
    console.print(Panel(f"[bold {decision_color}]FINAL DECISION: {result['decision']}[/bold {decision_color}]", 
                        title="[bold]3. PORTFOLIO MANAGER VERDICT[/bold]", border_style=decision_color))

if __name__ == "__main__":
    asyncio.run(run_analysis_cli())