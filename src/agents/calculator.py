import pandas as pd
import numpy as np

def get_fin_val(df: pd.DataFrame, keys: list, default=0.0):
    """
    Looks for multiple potential row names (keys) and returns the first found value.
    """
    if df is None or df.empty: return default
    # Normalize index to avoid case/space issues
    df.index = df.index.str.strip()
    for key in keys:
        if key in df.index:
            # iloc[0] assumes we want the most recent period (TTM or MRQ)
            val = df.loc[key].iloc[0] if isinstance(df.loc[key], pd.Series) else df.loc[key]
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

# =======================================
# Financial Metrics
# =======================================

def calculate_sloan_ratio(financials, cashflow, balance_sheet):
    net_income = get_fin_val(financials, ['Net Income', 'Net Income Common Stockholders'])
    cfo = get_fin_val(cashflow, ['Cash Flow From Continuing Operating Activities', 'Operating Cash Flow'])
    total_assets = get_fin_val(balance_sheet, ['Total Assets'])
    
    if total_assets == 0: return 0.0
    return (net_income - cfo) / total_assets

def calculate_roic(financials, balance_sheet):
    ebit = get_fin_val(financials, ['EBIT', 'Operating Income'])
    # Dynamic tax rate calculation
    pretax = get_fin_val(financials, ['Pretax Income'], default=1.0)
    tax_prov = get_fin_val(financials, ['Tax Provision'], default=0.0)
    tax_rate = max(0, min(tax_prov / pretax, 0.35)) if pretax > 0 else 0.21
    
    nopat = ebit * (1 - tax_rate)
    
    debt = get_fin_val(balance_sheet, ['Total Debt', 'Long Term Debt'])
    equity = get_fin_val(balance_sheet, ['Stockholders Equity', 'Total Stockholder Equity'])
    cash = get_fin_val(balance_sheet, ['Cash And Cash Equivalents', 'Cash'])
    
    invested_capital = (debt + equity) - cash
    return nopat / invested_capital if invested_capital > 0 else 0.0
    
def calculate_wacc(ticker_info: dict, financials: pd.DataFrame, balance_sheet: pd.DataFrame, cashflow: pd.DataFrame) -> float:
    """
    Formula: (E/V * Re) + (D/V * Rd * (1 - Tc))
    Edge Logic: If ROIC < WACC, the company is a 'Value Destroyer'.
    """
    try:
        # 1. Market Value of Equity (E) and Total Debt (D)
        market_cap = ticker_info.get('marketCap') or ticker_info.get('enterpriseValue', 0)
        total_debt = get_fin_val(balance_sheet, ['Total Debt', 'Long Term Debt'])
        total_value = market_cap + total_debt
        
        if total_value <= 0: return 0.08 # Institutional average fallback
        
        # 2. Cost of Equity (Re) using CAPM
        # 2026 Proxy: 10Y Treasury (~4.3%) + (Beta * Equity Risk Premium ~5.0%)
        rf = 0.043 
        erp = 0.050
        beta = ticker_info.get('beta')
        if beta is None or pd.isna(beta):
            beta = 1.0 # Market average proxy
            
        cost_of_equity = rf + (beta * erp)
        
        # 3. Cost of Debt (Rd) and Tax Rate (Tc)
        interest_exp = abs(get_fin_val(cashflow, ['Interest Expense', 'Interest Paid Supplementals']))
        # Rd = Interest Expense / Total Debt. If no debt, Rd is irrelevant.
        cost_of_debt = (interest_exp / total_debt) if total_debt > 0 else 0.05
        
        # Effective Tax Rate
        pretax_inc = get_fin_val(financials, ['Pretax Income'], default=1.0)
        tax_prov = get_fin_val(financials, ['Tax Provision'], default=0.0)
        tax_rate = max(0, min(tax_prov / pretax_inc, 0.35)) if pretax_inc > 0 else 0.21
        
        # 4. Final Weighting
        w_equity = market_cap / total_value
        w_debt = total_debt / total_value
        
        wacc = (w_equity * cost_of_equity) + (w_debt * cost_of_debt * (1 - tax_rate))
        return float(wacc)
        
    except Exception as e:
        print(f"WACC Error: {e}")
        return 0.08 # Standard 'Hurdle Rate' fallback
    

# =======================================
# Quantitative Metrics
# =======================================

def calculate_rolling_sortino(returns: pd.Series, rf: float = 0.04) -> float:
    if len(returns) < 30: return 0.0 # Need sufficient sample size
    excess = returns - (rf / 252)
    downside = excess[excess < 0]
    if len(downside) < 2: return 0.0
    
    dd_std = downside.std() * np.sqrt(252)
    return (excess.mean() * 252) / dd_std if dd_std != 0 else 0.0

def calculate_cvar_95(returns: pd.Series) -> float:
    if returns.empty: return 0.0
    var_95 = np.nanpercentile(returns, 5)
    tail_loss = returns[returns <= var_95]
    return abs(tail_loss.mean()) if not tail_loss.empty else 0.0

def calculate_beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Formula: Cov(Rp, Rm) / Var(Rm)
    Edge Logic: Identifies Systemic Risk. A Beta > 1.3 in a high-volatility 
    market is a 'Volatility Trap' for most retail portfolios.
    """
    try:
        # 1. Cleaning & Alignment
        # We must drop NaNs and align indices to ensure we compare the same trading days
        combined = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
        
        if len(combined) < 30: # Statistical significance threshold
            return 1.0
        
        # 2. Calculation using the Covariance Matrix
        # matrix[0,1] is Cov(Asset, Market), matrix[1,1] is Var(Market)
        covariance_matrix = np.cov(combined.iloc[:, 0], combined.iloc[:, 1])
        covariance = covariance_matrix[0, 1]
        benchmark_variance = covariance_matrix[1, 1]
        
        beta = covariance / benchmark_variance if benchmark_variance != 0 else 1.0
        
        # 3. Architect's Cap: Winsorizing
        # We cap Beta at 4.0 and floor at -1.0 to prevent outlier data from breaking WACC
        return float(np.clip(beta, -1.0, 4.0))

    except Exception as e:
        print(f"Beta Calculation Error: {e}")
        return 1.0 # Default to market risk

def calculate_asset_turnover(financials, balance_sheet):
    revenue = get_fin_val(financials, ['Total Revenue', 'Revenue'])
    assets = get_fin_val(balance_sheet, ['Total Assets'])
    return revenue / assets if assets > 0 else 0.0

def calculate_altman_z(financials, balance_sheet):
    """Simplified Z-Score for Public Co's"""
    rev = get_fin_val(financials, ['Total Revenue'])
    ebit = get_fin_val(financials, ['EBIT'])
    assets = get_fin_val(balance_sheet, ['Total Assets'])
    retained_earnings = get_fin_val(balance_sheet, ['Retained Earnings'])
    working_cap = get_fin_val(balance_sheet, ['Working Capital'], default=0.0)
    # Market Cap / Total Liab (simplified proxy)
    liab = get_fin_val(balance_sheet, ['Total Liabilities Net Minority Interest', 'Total Liabilities'])
    
    if assets == 0: return 0.0
    
    # Weights for public manufacturing firms
    z = (1.2 * (working_cap/assets)) + (1.4 * (retained_earnings/assets)) + \
        (3.3 * (ebit/assets)) + (0.99 * (rev/assets))
    return z

def calculate_ccc(financials, balance_sheet):
    rev = get_fin_val(financials, ['Total Revenue'])
    cogs = get_fin_val(financials, ['Cost Of Revenue'])
    inv = get_fin_val(balance_sheet, ['Inventory'])
    ar = get_fin_val(balance_sheet, ['Accounts Receivable'])
    ap = get_fin_val(balance_sheet, ['Accounts Payable'])
    
    if rev == 0 or cogs == 0: return 0.0
    
    dio = (inv / cogs) * 365
    dso = (ar / rev) * 365
    dpo = (ap / cogs) * 365
    return dio + dso - dpo

def generate_alpha_score(roic, wacc, sloan, z_score, sortino, beta):
    """
    The Architect's Final Verdict (0-100 Score)
    """
    score = 0
    
    # 1. Economic Value Add (30%)
    spread = roic - wacc
    if spread > 0.05: score += 30
    elif spread > 0: score += 15
    
    # 2. Earnings Quality (25%)
    if -0.1 < sloan < 0.1: score += 25
    elif 0.1 <= sloan < 0.2: score += 10
    
    # 3. Survival (20%)
    if z_score > 3.0: score += 20
    elif z_score > 1.8: score += 10
    
    # 4. Risk-Adjusted Return (25%)
    if sortino > 2.0: score += 25
    elif sortino > 1.0: score += 15
    
    # Penalty: High Systemic Risk
    if beta > 1.5: score -= 10
    
    return max(0, min(score, 100))

# Edge Logic: This 'Confluence Score' prevents a user from buying a 
# high-ROIC stock that is actually a forensic fraud (High Sloan).