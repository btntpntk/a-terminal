"""
DRSI (Dual RSI) Strategy.

DRSI = (RSI_stock * 0.4) + (RSI_stock / RSI_benchmark * 0.4) + (RSI_benchmark * 0.2)

  Long  when DRSI > 48
  Short when DRSI crosses below its MA (DRSI[t] < MA[t] and DRSI[t-1] >= MA[t-1])

Requires benchmark_prices to be passed as a kwarg from the engine.
"""

from __future__ import annotations

import pandas as pd

from src.backtesting.interfaces import TradingStrategy


def _sma_rsi(series: pd.Series | pd.DataFrame, window: int) -> pd.Series | pd.DataFrame:
    """Simple-average (Wilder-style SMA) RSI."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


class DRSIStrategy(TradingStrategy):
    name = "DRSI Strategy"
    supports_short = False

    def __init__(self, rsi_period: int = 14, ma_period: int = 20):
        self.rsi_period = rsi_period
        self.ma_period  = ma_period

    def generate_signals(self, prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
        benchmark_prices: pd.Series | None = kwargs.get("benchmark_prices")
        if benchmark_prices is None:
            raise ValueError("DRSIStrategy requires benchmark_prices to be passed via kwargs.")

        # Align benchmark to the same index (ffill for weekends/holidays, bfill for leading gaps)
        bm = benchmark_prices.reindex(prices.index).ffill().bfill()

        # RSI for each stock and for the benchmark
        rsi_stock = _sma_rsi(prices, self.rsi_period)   # DataFrame
        rsi_bench = _sma_rsi(bm, self.rsi_period)        # Series

        # Broadcast benchmark RSI across all asset columns
        rsi_bench_df = pd.DataFrame(
            {col: rsi_bench for col in prices.columns},
            index=prices.index,
        )

        # Guard against division by zero (rsi_bench can be 0 during warm-up)
        safe_rsi_bench = rsi_bench_df.replace(0, float("nan"))

        # DRSI formula
        drsi = (rsi_stock * 0.4) + ((rsi_stock / safe_rsi_bench) * 0.4) + (rsi_bench_df * 0.2)

        # MA of DRSI (used for short signal)
        drsi_ma = drsi.rolling(window=self.ma_period).mean()

        signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        # Long: DRSI > 48
        signals[drsi > 48] = 1.0

        # Exit: DRSI crosses MA downward — go flat (no short)
        exit_condition = (drsi < drsi_ma) & (drsi.shift(1) >= drsi_ma.shift(1))
        signals[exit_condition] = 0.0

        return signals.fillna(0.0)
