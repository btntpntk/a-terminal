import yfinance as yf
from src.agents.calculator import calculate_sloan_ratio, calculate_cvar_95, calculate_wacc, calculate_roic, calculate_rolling_sortino, calculate_beta,calculate_asset_turnover,calculate_altman_z,calculate_ccc, generate_alpha_score # etc

ticker = "CPALL.BK"

stock = yf.Ticker(ticker)
hist = stock.history(period="1y")['Close']
returns = hist.pct_change().dropna()

balance_sheet = stock.balance_sheet
total_debt = balance_sheet.loc['Total Debt'].iloc[0]

sloan_ratio = calculate_sloan_ratio(stock.financials, stock.cashflow, stock.balance_sheet)
wacc = calculate_wacc(stock.info, stock.financials, stock.balance_sheet, stock.cashflow)
roic = calculate_roic(stock.financials, stock.balance_sheet)

cvar_95 = calculate_cvar_95(returns)
r_sortino = calculate_rolling_sortino(returns)
# calculate_beta()
asset_turnover = calculate_asset_turnover(stock.financials, stock.balance_sheet)
altman_z = calculate_altman_z(stock.financials, stock.balance_sheet)
ccc = calculate_ccc(stock.financials, stock.balance_sheet)

print("S-Ratio:", sloan_ratio)
print("WACC:", wacc)
print("ROIC:", roic)
print("CVar_95:", cvar_95)
print("R_Sortino:", r_sortino)
print("Asset Turnover:", asset_turnover)
print("Altman Z:", altman_z)
print("CCC:", ccc)

alpha_score = generate_alpha_score(roic, wacc, sloan_ratio, altman_z, r_sortino, 0)
print("Alpha Score:", alpha_score)