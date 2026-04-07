"""
src/universes  —  canonical home for all tradable universe definitions.

Each universe lives in its own file for easy extension.

Import from here in new code:
    from src.universes import UNIVERSE_MAP
    from src.universes.sp500_sample import SP500_SAMPLE
"""

from .sp500_sample   import SP500_SAMPLE
from .thai_large_cap import THAI_LARGE_CAP
from .crypto_majors  import CRYPTO_MAJORS
from .global_etf     import GLOBAL_ETF
from .watchlist_a    import WATCHLIST_A

UNIVERSE_MAP: dict = {
    "SP500_SAMPLE":   SP500_SAMPLE,
    "THAI_LARGE_CAP": THAI_LARGE_CAP,
    "CRYPTO_MAJORS":  CRYPTO_MAJORS,
    "GLOBAL_ETF":     GLOBAL_ETF,
    "WATCHLIST_A":    WATCHLIST_A,
}

__all__ = [
    "SP500_SAMPLE",
    "THAI_LARGE_CAP",
    "CRYPTO_MAJORS",
    "GLOBAL_ETF",
    "WATCHLIST_A",
    "UNIVERSE_MAP",
]
