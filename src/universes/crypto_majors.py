"""Top-5 crypto assets by market cap, benchmark BTC-USD."""

from src.backtesting.interfaces import Universe

CRYPTO_MAJORS = Universe(
    name="Crypto Majors",
    tickers=["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "ADA-USD"],
    benchmark_ticker="BTC-USD",
)
