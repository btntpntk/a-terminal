"""
backend/schemas.py
Pydantic v2 response models for all API endpoints.

Mirrors the exact dict keys produced by each pipeline stage.
Optional[float] used extensively — yfinance data is often incomplete.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# SHARED PRIMITIVES
# ─────────────────────────────────────────────────────────────

class SignalItem(BaseModel):
    """Standardised structure shared by every macro signal."""
    ticker:        str
    current_price: Optional[float] = None
    mom_20d_pct:   Optional[float] = None
    z_score_60d:   Optional[float] = None
    signal:        str
    risk_score:    int
    macro_bias:    str


# ─────────────────────────────────────────────────────────────
# STAGE 0 — MARKET FRAGILITY
# ─────────────────────────────────────────────────────────────

class LayerScores(BaseModel):
    regime:    float
    fragility: float
    trigger:   float

class RegimeSignal(BaseModel):
    signal:     str
    risk_score: int
    value:      Optional[float] = None
    note:       Optional[str]   = None

class RegimeResponse(BaseModel):
    # Composite
    composite_risk:   float
    regime_label:     str
    layer_scores:     LayerScores
    confidence:       float
    confidence_signal: str
    position_scale:   str          # "100% — Full Kelly" … "25% — Capital Preservation"
    # SPX vs 200DMA
    spx_distance_pct: Optional[float] = None
    spx_signal:       str = "N/A"
    spx_risk_score:   int = 50
    # Yield curve
    yield_spread_bps: Optional[float] = None
    yield_signal:     str = "N/A"
    yield_risk_score: int = 50
    # HY credit
    hy_oas_bps:       Optional[float] = None
    hy_signal:        str = "N/A"
    hy_risk_score:    int = 50
    # Breadth
    breadth_pct:      Optional[float] = None
    breadth_signal:   str = "N/A"
    breadth_risk_score: int = 50
    # RSP/SPY
    rsp_z_score:      Optional[float] = None
    rsp_signal:       str = "N/A"
    rsp_risk_score:   int = 50
    # VIX
    vix_level:        Optional[float] = None
    vix_percentile:   Optional[float] = None
    vix_signal:       str = "N/A"
    vix_risk_score:   int = 50
    # VIX term structure
    vix_roll_yield:   Optional[float] = None
    vix_term_signal:  str = "N/A"
    vix_term_risk_score: int = 50

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# STAGE 1 — GLOBAL MACRO
# ─────────────────────────────────────────────────────────────

class MacroSignalDetail(BaseModel):
    ticker:        str
    current_price: Optional[float] = None
    mom_20d_pct:   Optional[float] = None
    mom_60d_pct:   Optional[float] = None
    z_score_60d:   Optional[float] = None
    signal:        str
    risk_score:    int
    macro_bias:    str
    # Signal-specific extras (not all signals have all fields)
    yield_level:        Optional[float] = None   # real_yield
    yield_chg_20d:      Optional[float] = None   # real_yield
    real_yield_rising:  Optional[bool]  = None   # real_yield
    tip_mom_20d:        Optional[float] = None   # real_yield
    usdthb_rate:        Optional[float] = None   # thb
    eem_mom_20d:        Optional[float] = None   # em_flows
    spy_mom_20d:        Optional[float] = None   # em_flows
    em_alpha_20d:       Optional[float] = None   # em_flows
    thd_mom_20d:        Optional[float] = None   # em_flows
    mchi_mom_60d:       Optional[float] = None   # china
    kweb_mom_20d:       Optional[float] = None   # china
    note:               Optional[str]   = None

class MacroResponse(BaseModel):
    # 8 signals
    real_yield: MacroSignalDetail
    dxy:        MacroSignalDetail
    thb:        MacroSignalDetail
    crude_oil:  MacroSignalDetail
    copper:     MacroSignalDetail
    gold:       MacroSignalDetail
    em_flows:   MacroSignalDetail
    china:      MacroSignalDetail
    # Composite
    composite_macro_risk: float
    macro_regime:         str
    cycle_quadrant:       str
    quadrant_advice:      str
    copper_gold_ratio:    float
    macro_bias_summary:   str
    # Sector adjustments: {sector_name: int}
    sector_adjustments:   dict[str, int]
    raw_scores:           dict[str, int]
    signal_weights:       dict[str, float]

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# STAGE 2 — SECTOR SCREENER
# ─────────────────────────────────────────────────────────────

class SectorItem(BaseModel):
    sector:       str
    etf:          str
    sector_score: float
    mom_20d_pct:  float
    mom_60d_pct:  Optional[float] = None
    rs_vs_index:  float
    breadth_pct:  float
    volume_flow:  float
    macro_adj:    int
    signal:       str
    gate_pass:    bool

class SectorsResponse(BaseModel):
    universe:        str
    sector_gate:     bool
    sector_rotation: str
    top_sectors:     list[str]
    avoid_sectors:   list[str]
    ranked_sectors:  list[SectorItem]

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# STAGES 3+4 — TICKER RANKINGS
# ─────────────────────────────────────────────────────────────

class TickerRow(BaseModel):
    ticker:  str
    sector:  str
    price:   Optional[float] = None
    # Fundamentals
    alpha:        float
    roic:         Optional[float] = None   # percentage points, e.g. 14.2 means 14.2%
    wacc:         Optional[float] = None   # percentage points, e.g. 6.5 means 6.5%
    moat:         Optional[float] = None   # percentage points, e.g. +7.7 means ROIC 7.7pp above WACC
    z:            Optional[float] = None
    sloan:        Optional[float] = None
    fcf_q:        Optional[float] = None
    beta:         Optional[float] = None
    cvar:         Optional[float] = None   # percentage points, e.g. 1.8 means 1.8% daily tail loss
    sortino:      Optional[float] = None
    a_turn:       Optional[float] = None
    ccc:          Optional[float] = None
    sector_score: float
    sector_adj:   int
    # Technical
    strategy:   str
    regime_fit: Optional[str]  = None
    signal_str: int
    rr:         float
    entry:      Optional[float] = None
    tp:         Optional[float] = None
    sl:         Optional[float] = None
    atr:        Optional[float] = None
    # Gates & ranking
    gate3:      bool
    gate4:      bool
    rank_score: float
    verdict:    str    # "BUY" | "FUND_ONLY" | "TECH_ONLY" | "FAIL"


class RankingsResponse(BaseModel):
    universe:      str
    total_scanned: int
    buy_count:     int
    failed_count:  int
    composite_risk: float
    macro_regime:   str
    cycle_quadrant: str
    rows:          list[TickerRow]
    errors:        list[dict[str, str]]

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# SCAN JOB
# ─────────────────────────────────────────────────────────────

class ScanProgress(BaseModel):
    job_id:       str
    status:       str          # "pending" | "running" | "completed" | "failed"
    universe:     str
    total:        int
    completed:    int
    progress_pct: float
    started_at:   datetime
    completed_at: Optional[datetime] = None
    error:        Optional[str]      = None


class ScanResult(ScanProgress):
    rankings: Optional[RankingsResponse] = None


# ─────────────────────────────────────────────────────────────
# UNIVERSE CONFIG
# ─────────────────────────────────────────────────────────────

class UniverseInfo(BaseModel):
    key:          str
    display_name: str
    ticker_count: int
    sector_count: int
    benchmark:    str

class UniversesResponse(BaseModel):
    universes: list[UniverseInfo]


# ─────────────────────────────────────────────────────────────
# HMM REGIME
# ─────────────────────────────────────────────────────────────

class HMMRegimeStat(BaseModel):
    frequency_pct:    float
    avg_duration_days: float
    ann_return_pct:   float
    ann_vol_pct:      float


class HMMRegimePoint(BaseModel):
    date:       str
    regime:     str
    p_bull:     float
    p_sideways: float
    p_bear:     float
    p_crash:    float
    close:      Optional[float] = None


class HMMRegimeResponse(BaseModel):
    ticker:          str
    current_regime:  str
    current_p_bull:  float
    current_p_side:  float
    current_p_bear:  float
    current_p_crash: float
    train_end:       str
    test_start:      str
    n_observations:  int
    regime_stats:    dict[str, HMMRegimeStat]
    series:          list[HMMRegimePoint]
