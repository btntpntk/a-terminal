"""Diversified global ETF universe spanning equities, bonds, commodities, REITs."""

from src.backtesting.interfaces import Universe

GLOBAL_ETF = Universe(
    name="Global ETF",
    tickers=["SPY", "QQQ", "EEM", "GLD", "TLT", "IWM", "EFA", "VNQ", "HYG", "DBC"],
    benchmark_ticker="SPY",
)
