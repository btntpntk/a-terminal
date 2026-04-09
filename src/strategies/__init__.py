"""
src/strategies  —  canonical home for all trading strategy implementations.

Import from here in new code:
    from src.strategies import STRATEGY_MAP
    from src.strategies.momentum import MomentumStrategy
"""

from .momentum              import MomentumStrategy
from .mean_reversion        import MeanReversionStrategy
from .moving_average_cross  import MovingAverageCrossStrategy
from .ema_cross             import EMACrossStrategy
from .rsi                   import RSIStrategy
from .volatility_breakout   import VolatilityBreakoutStrategy
from .drsi                  import DRSIStrategy

STRATEGY_MAP: dict = {
    "MomentumStrategy":           MomentumStrategy,
    "MeanReversionStrategy":      MeanReversionStrategy,
    "MovingAverageCrossStrategy": MovingAverageCrossStrategy,
    "EMACrossStrategy":           EMACrossStrategy,
    "RSIStrategy":                RSIStrategy,
    "VolatilityBreakoutStrategy": VolatilityBreakoutStrategy,
    "DRSIStrategy":               DRSIStrategy,
}

__all__ = [
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "EMACrossStrategy",
    "RSIStrategy",
    "VolatilityBreakoutStrategy",
    "DRSIStrategy",
    "STRATEGY_MAP",
]
