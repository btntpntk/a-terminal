"""
src/universes  —  canonical home for all tradable universe definitions.

Each universe lives in its own file for easy extension.

Import from here in new code:
    from src.universes import UNIVERSE_MAP, UNIVERSE_REGISTRY
    from src.universes.sp500_sample import SP500_SAMPLE
"""

from .sp500_sample   import SP500_SAMPLE
from .set100 import SET100
from .crypto_majors  import CRYPTO_MAJORS
from .global_etf     import GLOBAL_ETF
from .watchlist_a    import WATCHLIST_A

UNIVERSE_MAP: dict = {
    "SP500_SAMPLE":   SP500_SAMPLE,
    "SET100":         SET100,
    "CRYPTO_MAJORS":  CRYPTO_MAJORS,
    "GLOBAL_ETF":     GLOBAL_ETF,
    "WATCHLIST_A":    WATCHLIST_A,
}

# Derived registry for the scan pipeline — only universes with sector data.
# Shape: key -> {"display_name", "universe" (sector map), "benchmark", "fallback_benchmark"}
UNIVERSE_REGISTRY: dict = {
    key: {
        "display_name":       u.display_name,
        "universe":           u.sectors,
        "benchmark":          u.benchmark_ticker,
        "fallback_benchmark": u.fallback_benchmark or u.benchmark_ticker,
    }
    for key, u in UNIVERSE_MAP.items()
    if u.sectors is not None
}

__all__ = [
    "SP500_SAMPLE",
    "SET100",
    "CRYPTO_MAJORS",
    "GLOBAL_ETF",
    "WATCHLIST_A",
    "UNIVERSE_MAP",
    "UNIVERSE_REGISTRY",
]
