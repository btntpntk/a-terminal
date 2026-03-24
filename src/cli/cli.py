import asyncio
import questionary
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from src.data.providers import fetch_all_data
from src.graph.graph import hedge_fund_app

console = Console()

async def run_cli():
    console.print(Panel("[bold green]ALPHA-STREAM ARCHITECT: COMMAND CENTER[/bold green]"))
    
    ticker = await questionary.text("Enter Ticker:").ask_async()
    if not ticker: return

    with console.status(f"[bold yellow]Analyzing {ticker}...", spinner="dots"):
        # 1. Fetch Data
        market_data = await fetch_all_data(ticker)
        
        # 2. Run Multi-Agent Graph
        # Edge Logic: We pass the data once, and agents process it in memory.
        result = await hedge_fund_app.ainvoke({
            "ticker": ticker,
            "data": market_data,
            "analysis_steps": [],
            "metadata": {}
        })

    # 3. Render Dashboard
    table = Table(title=f"Committee Findings: {ticker}")
    table.add_column("Agent", style="cyan")
    table.add_column("Reasoning", style="white")

    for step in result["analysis_steps"]:
        agent, reason = step.split(":", 1)
        table.add_row(agent, reason.strip())

    console.print(table)
    console.print(Panel(f"[bold]FINAL DECISION: {result['decision']}[/bold]", border_style="green"))

if __name__ == "__main__":
    asyncio.run(run_cli())