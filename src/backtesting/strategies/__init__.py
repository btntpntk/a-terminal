# Shim — canonical implementations live in src/strategies/.
# This module re-exports everything so existing imports keep working.

from src.strategies import (          # noqa: F401
    MomentumStrategy,
    MeanReversionStrategy,
    MovingAverageCrossStrategy,
    RSIStrategy,
    VolatilityBreakoutStrategy,
    STRATEGY_MAP,
)

__all__ = [
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "RSIStrategy",
    "VolatilityBreakoutStrategy",
    "STRATEGY_MAP",
]
