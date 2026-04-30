"""S&P 500 large-cap universe — 11 GICS sectors, benchmark SPY."""

from src.backtesting.interfaces import Universe

_SECTORS = {
    "TECH":          {"etf": "XLK",  "members": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "CSCO", "AMAT", "QCOM"]},
    "HEALTH":        {"etf": "XLV",  "members": ["UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "ISRG"]},
    "FINANCIALS":    {"etf": "XLF",  "members": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP"]},
    "CONSUMER_DISC": {"etf": "XLY",  "members": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TGT", "GM"]},
    "COMM_SERVICES": {"etf": "XLC",  "members": ["META", "GOOGL", "NFLX", "DIS", "TMUS", "VZ", "T", "CMCSA", "EA", "TTWO"]},
    "INDUSTRIALS":   {"etf": "XLI",  "members": ["GE", "CAT", "HON", "RTX", "UPS", "LMT", "DE", "BA", "FDX", "CSX"]},
    "CONSUMER_STAP": {"etf": "XLP",  "members": ["WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "CL", "MDLZ", "KHC"]},
    "ENERGY":        {"etf": "XLE",  "members": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL"]},
    "UTILITIES":     {"etf": "XLU",  "members": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "ETR"]},
    "REAL_ESTATE":   {"etf": "XLRE", "members": ["PLD", "AMT", "EQIX", "CCI", "PSA", "SPG", "WELL", "DLR", "O", "AVB"]},
    "MATERIALS":     {"etf": "XLB",  "members": ["LIN", "APD", "ECL", "SHW", "FCX", "NEM", "NUE", "VMC", "MLM", "ALB"]},
}

SP500_SAMPLE = Universe(
    name="SP500_SAMPLE",
    display_name="S&P 500 Large-Cap",
    tickers=list(dict.fromkeys(t for s in _SECTORS.values() for t in s["members"])),
    benchmark_ticker="SPY",
    fallback_benchmark="^GSPC",
    sectors=_SECTORS,
)
