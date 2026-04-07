"""S&P 500 mega-cap sample — 10 largest names, benchmark SPY."""

from src.backtesting.interfaces import Universe

SP500_SAMPLE = Universe(
    name="S&P 500 Sample",
    tickers=[
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "TSLA", "NVDA", "JPM", "JNJ", "XOM",
    ],
    benchmark_ticker="SPY",
)
