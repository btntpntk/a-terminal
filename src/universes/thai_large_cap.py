"""Thai large-cap universe — SET100 blue chips, benchmark ^SET.BK."""

from src.backtesting.interfaces import Universe

THAI_LARGE_CAP = Universe(
    name="Thai Large Cap",
    tickers=[
        "PTT.BK", "KBANK.BK", "SCB.BK",    "AOT.BK",   "CPALL.BK",
        "GULF.BK","ADVANC.BK","BBL.BK",     "MINT.BK",  "BDMS.BK",
    ],
    benchmark_ticker="^SET.BK",
)
