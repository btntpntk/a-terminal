"""
Watchlist A  —  44-stock mixed universe (SET blue chips + NYSE:BKV).
benchmark: ^SET.BK

Excluded from original list (not available via yfinance):
  TFEX:S501!   — SET50 futures continuous contract (no spot data)
  SET:PF_REIT  — PF-REIT.BK not found / delisted on Yahoo Finance
"""

from src.backtesting.interfaces import Universe

WATCHLIST_A = Universe(
    name="Watchlist A",
    tickers=[
        # SET large-caps & mid-caps  (.BK suffix)
        "ADVANC.BK", "AOT.BK",    "BANPU.BK",  "BBL.BK",    "BCH.BK",
        "BDMS.BK",   "BH.BK",     "CPALL.BK",  "CPAXT.BK",  "CPN.BK",
        "CRC.BK",    "DELTA.BK",  "EGCO.BK",   "ERW.BK",    "GLOBAL.BK",
        "GULF.BK",   "HL.BK",     "HMPRO.BK",  "KBANK.BK",  "KCE.BK",
        "KTB.BK",    "LH.BK",     "MEGA.BK",   "MINT.BK",   "NEO.BK",
        "NKT.BK",    "OR.BK",     "OSP.BK",    "PR9.BK",    "PTT.BK",
        "PTTEP.BK",  "RATCH.BK",  "RBF.BK",    "SABINA.BK", "SCB.BK",
        "SCC.BK",    "SFLEX.BK",  "SIS.BK",    "SISB.BK",   "SPALI.BK",
        "TIDLOR.BK", "TTB.BK",    "WHA.BK",
        # NYSE
        "BKV",
    ],
    benchmark_ticker="^SET.BK",
)
