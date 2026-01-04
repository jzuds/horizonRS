import math
import statistics

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

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

def stability_score(values):
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return clamp(1 - (statistics.stdev(values) / mean))

def liquidity_score(volume, fill_speed_score):
    return

def risk_score(mid_prices, volume_history):
    return