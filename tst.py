import yfinance as yf
from src.agents.calculator import calculate_sloan_ratio, calculate_cvar_95, calculate_wacc, calculate_roic # etc

ticker = "AAPL"

stock = yf.Ticker(ticker)
hist = stock.history(period="1y")['Close']
returns = hist.pct_change().dropna()

balance_sheet = stock.balance_sheet
total_debt = balance_sheet.loc['Total Debt'].iloc[0]
print(total_debt)


# print("WACC:")
# print(calculate_wacc(stock.info, stock.financials, stock.balance_sheet, stock.cashflow))

print("ROIC:")
print(stock.financials.index.to_list())

# print("S-Ratio")
# print(calculate_sloan_ratio(stock.financials, stock.cashflow, stock.balance_sheet))