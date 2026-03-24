import yfinance as yf
import pandas as pd

async def fetch_all_data(ticker: str):
    """
    Institutional data aggregator.
    Returns raw ticker objects and processed returns for quantitative analysis.
    """
    # Initialize the Ticker object
    stock = yf.Ticker(ticker)
    
    # Edge Logic: We fetch 1y of history to support 90D rolling risk metrics and CVaR.
    # Using 'Close' prices for return calculations.
    history = stock.history(period="1y")
    
    if history.empty:
        raise ValueError(f"No price history found for ticker: {ticker}")

    # Calculate daily returns for the 'returns' variable in your CLI
    returns = history['Close'].pct_change().dropna()
    
    # Edge Logic: Returning 'raw_stock_obj' allows the CLI and Agents to access 
    # .financials, .balance_sheet, and .cashflow without re-fetching.
    return {
        "ticker": ticker,
        "raw_stock_obj": stock,  # The yfinance Ticker object
        "prices": history,
        "returns": returns,
        "info": stock.info,      # Snapshot metrics like marketCap and beta
        "metrics": {
            "fwd_pe": stock.info.get("forwardPE"),
            "debt_to_equity": stock.info.get("debtToEquity")
        }
    }