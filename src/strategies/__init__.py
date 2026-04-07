"""
src/strategies  —  canonical home for all trading strategy implementations.

Import from here in new code:
    from src.strategies import STRATEGY_MAP
    from src.strategies.momentum import MomentumStrategy
"""

from .momentum              import MomentumStrategy
from .mean_reversion        import MeanReversionStrategy
from .moving_average_cross  import MovingAverageCrossStrategy
from .rsi                   import RSIStrategy
from .volatility_breakout   import VolatilityBreakoutStrategy

STRATEGY_MAP: dict = {
    "MomentumStrategy":           MomentumStrategy,
    "MeanReversionStrategy":      MeanReversionStrategy,
    "MovingAverageCrossStrategy": MovingAverageCrossStrategy,
    "RSIStrategy":                RSIStrategy,
    "VolatilityBreakoutStrategy": VolatilityBreakoutStrategy,
}

__all__ = [
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "RSIStrategy",
    "VolatilityBreakoutStrategy",
    "STRATEGY_MAP",
]
