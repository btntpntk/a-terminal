from .equal_weight import EqualWeightOptimizer
from .inverse_vol import InverseVolatilityOptimizer
from .mean_variance import MeanVarianceOptimizer
from .risk_parity import RiskParityOptimizer
from .kelly import KellyCriterionOptimizer

OPTIMIZER_MAP = {
    "EqualWeightOptimizer":        EqualWeightOptimizer,
    "InverseVolatilityOptimizer":  InverseVolatilityOptimizer,
    "MeanVarianceOptimizer":       MeanVarianceOptimizer,
    "RiskParityOptimizer":         RiskParityOptimizer,
    "KellyCriterionOptimizer":     KellyCriterionOptimizer,
}
