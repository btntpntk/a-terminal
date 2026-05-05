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
from .vader                 import VADERStrategy

# ── PineScript-derived strategies ────────────────────────────────────────────
from .pivot_point_supertrend    import PivotPointSupertrendStrategy
from .laguerre_rsi              import LaguerreRSIStrategy
from .hurst_choppiness          import HurstChoppinessStrategy
from .mansfield_minervini       import MansfieldMinerviniStrategy
from .wvf_connors_rsi           import WVFConnorsRSIStrategy
from .chandelier_exit           import ChandelierExitStrategy
from .banker_fund_flow          import BankerFundFlowStrategy
from .cpr_camarilla             import CPRCamarillaStrategy
from .position_cost_distribution import PositionCostDistributionStrategy
from .set_swing_dashboard       import SETSwingDashboardStrategy

STRATEGY_MAP: dict = {
    # Original strategies
    "MomentumStrategy":           MomentumStrategy,
    "MeanReversionStrategy":      MeanReversionStrategy,
    "MovingAverageCrossStrategy": MovingAverageCrossStrategy,
    "EMACrossStrategy":           EMACrossStrategy,
    "RSIStrategy":                RSIStrategy,
    "VolatilityBreakoutStrategy": VolatilityBreakoutStrategy,
    "DRSIStrategy":               DRSIStrategy,
    "VADERStrategy":              VADERStrategy,
    # PineScript-derived strategies
    "PivotPointSupertrendStrategy":     PivotPointSupertrendStrategy,
    "LaguerreRSIStrategy":             LaguerreRSIStrategy,
    "HurstChoppinessStrategy":         HurstChoppinessStrategy,
    "MansfieldMinerviniStrategy":      MansfieldMinerviniStrategy,
    "WVFConnorsRSIStrategy":           WVFConnorsRSIStrategy,
    "ChandelierExitStrategy":          ChandelierExitStrategy,
    "BankerFundFlowStrategy":          BankerFundFlowStrategy,
    "CPRCamarillaStrategy":            CPRCamarillaStrategy,
    "PositionCostDistributionStrategy": PositionCostDistributionStrategy,
    "SETSwingDashboardStrategy":       SETSwingDashboardStrategy,
}

__all__ = [
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MovingAverageCrossStrategy",
    "EMACrossStrategy",
    "RSIStrategy",
    "VolatilityBreakoutStrategy",
    "DRSIStrategy",
    "VADERStrategy",
    "PivotPointSupertrendStrategy",
    "LaguerreRSIStrategy",
    "HurstChoppinessStrategy",
    "MansfieldMinerviniStrategy",
    "WVFConnorsRSIStrategy",
    "ChandelierExitStrategy",
    "BankerFundFlowStrategy",
    "CPRCamarillaStrategy",
    "PositionCostDistributionStrategy",
    "SETSwingDashboardStrategy",
    "STRATEGY_MAP",
]
