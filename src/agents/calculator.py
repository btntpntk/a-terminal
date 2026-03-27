"""
src/agents/calculator.py
Financial & Quantitative Metrics Engine

Changes vs original:
  - calculate_altman_z: added the missing 0.6×(MarketCap/Liabilities) term
    → now matches the proper 5-variable Altman public-company model.
  - generate_alpha_score: beta now dynamically scales CVaR penalty based on
    the regime composite_risk score passed in from Stage 1.
  - calculate_fcf_quality: new function — FCF/NetIncome ratio for earnings quality.
  - generate_alpha_score: FCF quality integrated as a 5th scoring dimension.
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────
# CORE HELPERS  (unchanged)
# ─────────────────────────────────────────────────────────────

def get_fin_val(df: pd.DataFrame, keys: list, default=0.0):
    """
    Looks for multiple potential row names (keys) and returns the first found value.

    Matching strategy (in order):
      1. Exact match after stripping whitespace
      2. Case-insensitive + whitespace-collapsed match
         (handles yfinance returning 'OperatingIncome' vs 'Operating Income',
          'TotalRevenue' vs 'Total Revenue', etc. — common with non-US tickers)
    """
    if df is None or df.empty:
        return default
    df.index = df.index.str.strip()

    # Build a lowercase, space-collapsed lookup once — O(n) not O(n×k)
    index_lower = {k.lower().replace(" ", ""): k for k in df.index}

    for key in keys:
        # 1. Exact match
        if key in df.index:
            val = df.loc[key].iloc[0] if isinstance(df.loc[key], pd.Series) else df.loc[key]
            return float(val) if pd.notnull(val) else default
        # 2. Normalised match
        norm = key.lower().replace(" ", "")
        if norm in index_lower:
            actual = index_lower[norm]
            val = df.loc[actual].iloc[0] if isinstance(df.loc[actual], pd.Series) else df.loc[actual]
            return float(val) if pd.notnull(val) else default
    return default


def safe_scalar(val, default=np.nan):
    """Safely extract a scalar from Series/float/None."""
    if val is None:
        return default
    if isinstance(val, pd.Series):
        return float(val.iloc[-1]) if not val.empty else default
    try:
        return float(val)
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────
# FINANCIAL METRICS
# ─────────────────────────────────────────────────────────────

def calculate_sloan_ratio(financials, cashflow, balance_sheet) -> float:
    """
    Sloan Ratio = (Net Income − CFO) / Total Assets
    Range: <0.1 = clean accruals, >0.2 = potential earnings manipulation.
    """
    net_income   = get_fin_val(financials,    ['Net Income', 'Net Income Common Stockholders',
                                               'NetIncome', 'NetIncomeCommonStockholders'])
    cfo          = get_fin_val(cashflow,      ['Cash Flow From Continuing Operating Activities',
                                               'Operating Cash Flow',
                                               'CashFlowFromContinuingOperatingActivities',
                                               'OperatingCashFlow'])
    total_assets = get_fin_val(balance_sheet, ['Total Assets', 'TotalAssets'])

    if total_assets == 0:
        return 0.0
    return round((net_income - cfo) / total_assets, 4)


def calculate_roic(financials, balance_sheet) -> float:
    """
    ROIC = NOPAT / Invested Capital
    Invested Capital = (Total Debt + Equity) − Cash

    EBIT fallback chain:
      1. 'EBIT' / 'Ebit'
      2. 'Operating Income' / 'OperatingIncome'
      3. 'Income From Operations' / 'IncomeFromOperations'
      4. Gross Profit − Operating Expense (reconstructed)
    """
    ebit = get_fin_val(financials, ['EBIT', 'Ebit',
                                    'Operating Income', 'OperatingIncome',
                                    'Income From Operations', 'IncomeFromOperations',
                                    'Operating Profit', 'OperatingProfit'])

    # Last-resort reconstruction: Gross Profit − Total Operating Expenses
    if ebit == 0:
        gross   = get_fin_val(financials, ['Gross Profit', 'GrossProfit'])
        op_exp  = get_fin_val(financials, ['Operating Expense', 'OperatingExpense',
                                           'Total Operating Expenses', 'TotalOperatingExpenses'])
        if gross != 0 and op_exp != 0:
            ebit = gross - op_exp

    pretax   = get_fin_val(financials, ['Pretax Income', 'PretaxIncome'], default=1.0)
    tax_prov = get_fin_val(financials, ['Tax Provision', 'TaxProvision'], default=0.0)
    tax_rate = max(0, min(tax_prov / pretax, 0.35)) if pretax > 0 else 0.21

    nopat  = ebit * (1 - tax_rate)
    debt   = get_fin_val(balance_sheet, ['Total Debt', 'TotalDebt',
                                         'Long Term Debt', 'LongTermDebt'])
    equity = get_fin_val(balance_sheet, ['Stockholders Equity', 'StockholdersEquity',
                                         'Total Stockholder Equity', 'TotalStockholderEquity',
                                         'Total Equity Gross Minority Interest',
                                         'TotalEquityGrossMinorityInterest'])
    cash   = get_fin_val(balance_sheet, ['Cash And Cash Equivalents', 'CashAndCashEquivalents',
                                         'Cash Cash Equivalents And Short Term Investments',
                                         'CashCashEquivalentsAndShortTermInvestments', 'Cash'])

    invested_capital = (debt + equity) - cash
    return round(nopat / invested_capital, 4) if invested_capital > 0 else 0.0


def _resolve_market_cap(ticker_info: dict) -> float:
    """
    Robust market-cap resolution for any exchange.

    Priority:
      1. ticker_info['marketCap']  — direct field (may be None for non-US tickers)
      2. sharesOutstanding × current price  — computed (reliable for .BK, .HK, etc.)
      3. ticker_info['enterpriseValue']     — fallback (includes net debt, slight overcount)
      4. 0 — triggers WACC default below
    """
    mc = ticker_info.get('marketCap')
    if mc and float(mc) > 0:
        return float(mc)

    shares = float(ticker_info.get('sharesOutstanding') or
                   ticker_info.get('impliedSharesOutstanding') or 0)
    price  = float(ticker_info.get('currentPrice') or
                   ticker_info.get('regularMarketPrice') or
                   ticker_info.get('previousClose') or 0)
    computed = shares * price
    if computed > 0:
        return computed

    ev = ticker_info.get('enterpriseValue') or 0
    return float(ev)


def calculate_wacc(ticker_info: dict,
                   financials: pd.DataFrame,
                   balance_sheet: pd.DataFrame,
                   cashflow: pd.DataFrame) -> float:
    """
    WACC = (E/V × Re) + (D/V × Rd × (1−Tc))
    Uses CAPM for cost of equity. 2026 proxies: Rf=4.3%, ERP=5.0%.

    Robust for non-US tickers (.BK, .HK, etc.) where yfinance often omits
    marketCap — falls back to shares × price to avoid WACC collapsing to 0.
    """
    try:
        market_cap  = _resolve_market_cap(ticker_info)
        total_debt  = get_fin_val(balance_sheet, ['Total Debt', 'Long Term Debt',
                                                   'TotalDebt', 'LongTermDebt'])
        total_value = market_cap + total_debt

        if total_value <= 0:
            return 0.08

        rf, erp = 0.043, 0.050
        beta = ticker_info.get('beta')
        if beta is None or (isinstance(beta, float) and np.isnan(beta)):
            beta = 1.0
        cost_of_equity = rf + (float(beta) * erp)

        # Interest expense: income statement is the primary source;
        # cashflow 'Interest Paid Supplementals' is a reliable secondary.
        interest_exp = abs(get_fin_val(financials, ['Interest Expense', 'InterestExpense']))
        if interest_exp == 0:
            interest_exp = abs(get_fin_val(cashflow, ['Interest Paid Supplementals',
                                                       'Interest Expense',
                                                       'InterestPaidSupplementals']))
        # Cost of debt: use actual rate when available; floor at 4% if missing
        # to prevent a silent zero-cost-of-debt from collapsing WACC.
        if total_debt > 0 and interest_exp > 0:
            cost_of_debt = interest_exp / total_debt
        else:
            cost_of_debt = 0.04   # conservative floor (IG corporate)

        pretax_inc = get_fin_val(financials, ['Pretax Income', 'PretaxIncome'], default=1.0)
        tax_prov   = get_fin_val(financials, ['Tax Provision', 'TaxProvision'], default=0.0)
        tax_rate   = max(0, min(tax_prov / pretax_inc, 0.35)) if pretax_inc > 0 else 0.21

        w_equity = market_cap / total_value
        w_debt   = total_debt / total_value
        wacc = (w_equity * cost_of_equity) + (w_debt * cost_of_debt * (1 - tax_rate))
        return round(float(wacc), 4)

    except Exception as e:
        print(f"WACC Error: {e}")
        return 0.08


def calculate_fcf_quality(financials, cashflow) -> float:
    """
    FCF Quality = Free Cash Flow / Net Income
    NEW: Catches companies with high accounting income but poor cash conversion.

    Interpretation:
      > 1.0  = exceptional cash conversion (FCF exceeds reported income)
      0.6–1.0 = healthy
      0.3–0.6 = moderate concern
      < 0.3  = RED FLAG — income may be inflated by accruals

    Returns 0.0 if denominator is zero or negative.
    """
    net_income  = get_fin_val(financials, ['Net Income', 'NetIncome',
                                           'Net Income Common Stockholders',
                                           'NetIncomeCommonStockholders'])
    cfo         = get_fin_val(cashflow,   ['Cash Flow From Continuing Operating Activities',
                                           'CashFlowFromContinuingOperatingActivities',
                                           'Operating Cash Flow', 'OperatingCashFlow'])
    capex       = abs(get_fin_val(cashflow, ['Capital Expenditure', 'CapitalExpenditure',
                                             'Purchase Of PPE', 'PurchaseOfPPE',
                                             'Capital Expenditures', 'CapitalExpenditures'],
                                  default=0.0))

    fcf = cfo - capex
    if net_income <= 0:
        return 0.0
    return round(fcf / net_income, 4)


# ─────────────────────────────────────────────────────────────
# FIXED: ALTMAN Z-SCORE  (5-variable public company model)
# ─────────────────────────────────────────────────────────────

def calculate_altman_z(financials, balance_sheet,
                       ticker_info: dict = None) -> float:
    """
    Full 5-variable Altman Z-Score for public companies:

    Z = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 0.99×X5

    X1 = Working Capital / Total Assets
    X2 = Retained Earnings / Total Assets
    X3 = EBIT / Total Assets
    X4 = Market Cap / Total Liabilities   ← was missing in original
    X5 = Revenue / Total Assets

    Zones:
      Z > 2.99  → Safe
      1.81–2.99 → Grey zone
      Z < 1.81  → Distress
    """
    rev              = get_fin_val(financials,    ['Total Revenue', 'TotalRevenue',
                                                  'Revenue', 'Net Revenue', 'NetRevenue'])
    ebit             = get_fin_val(financials,    ['EBIT', 'Ebit',
                                                  'Operating Income', 'OperatingIncome',
                                                  'Income From Operations', 'IncomeFromOperations'])
    assets           = get_fin_val(balance_sheet, ['Total Assets', 'TotalAssets'])
    retained_earnings = get_fin_val(balance_sheet, ['Retained Earnings', 'RetainedEarnings'])
    working_cap      = get_fin_val(balance_sheet, ['Working Capital', 'WorkingCapital'], default=0.0)
    liabilities      = get_fin_val(balance_sheet, ['Total Liabilities Net Minority Interest',
                                                    'TotalLiabilitiesNetMinorityInterest',
                                                    'Total Liabilities', 'TotalLiabilities'])

    if assets == 0:
        return 0.0

    # X4: market cap / total liabilities — requires ticker_info
    if ticker_info is not None:
        market_cap = ticker_info.get('marketCap') or ticker_info.get('enterpriseValue', 0)
    else:
        # Fallback: use book equity as proxy (conservative)
        market_cap = get_fin_val(balance_sheet, ['Stockholders Equity', 'Total Stockholder Equity'])

    x1 = working_cap      / assets
    x2 = retained_earnings / assets
    x3 = ebit             / assets
    x4 = (market_cap / liabilities) if liabilities > 0 else 0.0
    x5 = rev              / assets

    z = (1.2 * x1) + (1.4 * x2) + (3.3 * x3) + (0.6 * x4) + (0.99 * x5)
    return round(z, 4)


# ─────────────────────────────────────────────────────────────
# QUANTITATIVE METRICS  (unchanged except docstrings)
# ─────────────────────────────────────────────────────────────

def calculate_rolling_sortino(returns: pd.Series, rf: float = 0.04) -> float:
    """Annualised Sortino ratio. Downside deviation uses only negative excess returns."""
    if len(returns) < 30:
        return 0.0
    excess   = returns - (rf / 252)
    downside = excess[excess < 0]
    if len(downside) < 2:
        return 0.0
    dd_std = downside.std() * np.sqrt(252)
    return round((excess.mean() * 252) / dd_std, 4) if dd_std != 0 else 0.0


def calculate_cvar_95(returns: pd.Series) -> float:
    """CVaR (Expected Shortfall) at 95% confidence. Magnitude of average tail loss."""
    if returns.empty:
        return 0.0
    var_95    = np.nanpercentile(returns, 5)
    tail_loss = returns[returns <= var_95]
    return round(abs(tail_loss.mean()), 6) if not tail_loss.empty else 0.0


def calculate_beta(asset_returns: pd.Series,
                   benchmark_returns: pd.Series) -> float:
    """
    Beta = Cov(Rp, Rm) / Var(Rm).
    Winsorised to [-1, 4] to prevent WACC blow-up.
    """
    try:
        combined = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
        if len(combined) < 30:
            return 1.0
        cov_matrix = np.cov(combined.iloc[:, 0], combined.iloc[:, 1])
        beta = cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] != 0 else 1.0
        return round(float(np.clip(beta, -1.0, 4.0)), 4)
    except Exception as e:
        print(f"Beta Calculation Error: {e}")
        return 1.0


def calculate_asset_turnover(financials, balance_sheet) -> float:
    """Revenue / Total Assets. Measures capital efficiency."""
    revenue = get_fin_val(financials,    ['Total Revenue', 'TotalRevenue', 'Revenue', 'Net Revenue'])
    assets  = get_fin_val(balance_sheet, ['Total Assets', 'TotalAssets'])
    return round(revenue / assets, 4) if assets > 0 else 0.0


def calculate_ccc(financials, balance_sheet) -> float:
    """
    Cash Conversion Cycle = DIO + DSO − DPO
    Lower (or negative) = more efficient working capital management.
    """
    rev  = get_fin_val(financials,    ['Total Revenue', 'TotalRevenue', 'Revenue'])
    cogs = get_fin_val(financials,    ['Cost Of Revenue', 'CostOfRevenue',
                                       'Cost Of Goods Sold', 'CostOfGoodsSold'])
    inv  = get_fin_val(balance_sheet, ['Inventory', 'Inventories'])
    ar   = get_fin_val(balance_sheet, ['Accounts Receivable', 'AccountsReceivable',
                                       'Net Receivables', 'NetReceivables'])
    ap   = get_fin_val(balance_sheet, ['Accounts Payable', 'AccountsPayable'])

    if rev == 0 or cogs == 0:
        return 0.0

    dio = (inv / cogs) * 365
    dso = (ar  / rev)  * 365
    dpo = (ap  / cogs) * 365
    return round(dio + dso - dpo, 2)


# ─────────────────────────────────────────────────────────────
# UPGRADED: ALPHA SCORE  (now 5 dimensions + regime scaling)
# ─────────────────────────────────────────────────────────────

def generate_alpha_score(roic: float,
                         wacc: float,
                         sloan: float,
                         z_score: float,
                         sortino: float,
                         beta: float,
                         fcf_quality: float = 1.0,
                         composite_risk: float = 50.0,
                         sector_macro_adj: int = 0) -> float:
    """
    Composite Alpha Score (0–100).

    Five scoring dimensions:
      1. Economic Value Add  30%  ROIC − WACC (moat quality)
      2. Earnings Quality    20%  Sloan ratio (accrual forensics)
      3. FCF Quality         10%  FCF/Net Income (NEW — cash vs income gap)
      4. Survival            20%  Altman Z-Score (bankruptcy distance)
      5. Risk-Adj Return     20%  Sortino ratio (return per unit of downside)

    Adjustments:
      - Beta penalty is now regime-scaled: in a high-risk market (composite_risk > 60),
        high-beta stocks suffer a larger deduction.
      - Sector macro adjustment is applied last (from global_macro.py).

    Parameters
    ----------
    composite_risk : float
        Stage 1 composite risk score (0–100). Higher = more penalising for beta.
    sector_macro_adj : int
        Sector-level macro bonus/penalty from global_macro.py (typically ±8).
    """
    score = 0.0

    # 1. Economic Value Add (30 pts)
    spread = roic - wacc
    if spread > 0.10:   score += 30
    elif spread > 0.05: score += 22
    elif spread > 0:    score += 12
    # Negative spread = value destroyer — no points

    # 2. Earnings Quality — Sloan (20 pts)
    if -0.05 < sloan < 0.05:    score += 20   # very clean
    elif -0.10 < sloan < 0.10:  score += 14
    elif 0.10 <= sloan < 0.20:  score += 6
    # High positive sloan = earnings inflation, no points

    # 3. FCF Quality (10 pts) — NEW
    if fcf_quality > 1.0:        score += 10   # FCF exceeds net income
    elif fcf_quality > 0.6:      score += 7
    elif fcf_quality > 0.3:      score += 3
    # Below 0.3 = red flag, no points

    # 4. Survival — Altman Z (20 pts)
    if z_score > 2.99:           score += 20
    elif z_score > 1.81:         score += 10
    # Below 1.81 = distress zone, no points

    # 5. Risk-Adjusted Return — Sortino (20 pts)
    if sortino > 2.5:            score += 20
    elif sortino > 1.5:          score += 15
    elif sortino > 1.0:          score += 9
    elif sortino > 0.5:          score += 4

    # ── Beta penalty (regime-scaled) ─────────────────────────
    # In calm markets (risk<40) the penalty is mild.
    # In stressed markets (risk≥100) high-beta is a volatility trap.
    # Range: risk=40 → 1.0×, risk=100 → 1.5×
    regime_multiplier = 1.0 + max(0, (composite_risk - 40) / 120)  # 1.0 to 1.5×
    if beta > 2.0:   score -= 15 * regime_multiplier
    elif beta > 1.5: score -= 10 * regime_multiplier
    elif beta > 1.3: score -= 5  * regime_multiplier

    # ── Macro sector adjustment ───────────────────────────────
    score += sector_macro_adj

    return round(float(max(0.0, min(100.0, score))), 1)