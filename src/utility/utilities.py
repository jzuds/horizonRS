import math

def calculate_profit(buy, sell, total_units=1, tax_rate=0.02, tax_cap=5_000_000, tax_exempt=50):
    total_buy = buy * total_units
    total_sell = sell * total_units
    raw = total_sell - total_buy
    if total_sell < tax_exempt:
        tax = 0
    else:
        tax = min(math.floor(total_sell * tax_rate), tax_cap)
    net_profit = raw - tax
    profit_pct = (net_profit / total_buy * 100) if total_buy > 0 else 0
    return (profit_pct, net_profit, raw, tax)
