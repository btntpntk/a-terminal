"""
Watchlist A  —  44-stock mixed universe (SET blue chips + NYSE:BKV).
benchmark: ^SET.BK

Excluded from original list (not available via yfinance):
  TFEX:S501!   — SET50 futures continuous contract (no spot data)
  SET:PF_REIT  — PF-REIT.BK not found / delisted on Yahoo Finance
"""

from src.backtesting.interfaces import Universe

_SECTORS = {
    "ENERGY":          {"etf": "PTT.BK",   "members": ["PTT.BK", "PTTEP.BK", "EGCO.BK", "RATCH.BK", "OR.BK", "BANPU.BK", "GULF.BK", "BKV"]},
    "FINANCIALS":      {"etf": "KBANK.BK", "members": ["BBL.BK", "KBANK.BK", "KTB.BK", "SCB.BK", "TIDLOR.BK", "TTB.BK", "NEO.BK"]},
    "TECH":            {"etf": "DELTA.BK", "members": ["DELTA.BK", "ADVANC.BK", "KCE.BK", "SIS.BK", "SFLEX.BK"]},
    "CONSUMER_DISC":   {"etf": "CPALL.BK", "members": ["CPALL.BK", "CPAXT.BK", "CRC.BK", "HMPRO.BK", "GLOBAL.BK", "OSP.BK", "ERW.BK", "MINT.BK", "SABINA.BK"]},
    "HEALTH":          {"etf": "BDMS.BK",  "members": ["BDMS.BK", "BH.BK", "BCH.BK", "MEGA.BK"]},
    "MATERIALS":       {"etf": "SCC.BK",   "members": ["SCC.BK"]},
    "REIT_PROPERTY":   {"etf": "CPN.BK",   "members": ["CPN.BK", "LH.BK", "WHA.BK", "SPALI.BK", "PF.BK"]},
    "INDUSTRIALS":     {"etf": "AOT.BK",   "members": ["AOT.BK"]},
    "WATCHLIST_OTHER": {"etf": "HL.BK",    "members": ["HL.BK", "NKT.BK", "PR9.BK", "RBF.BK", "SISB.BK"]},
}

WATCHLIST_A = Universe(
    name="WATCHLIST_A",
    display_name="Personal Watchlist",
    tickers=list(dict.fromkeys(t for s in _SECTORS.values() for t in s["members"])),
    benchmark_ticker="^SET.BK",
    fallback_benchmark="EWY",
    sectors=_SECTORS,
)
