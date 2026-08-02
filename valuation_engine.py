"""
valuation_engine.py
-------------------
Converts all VBA valuation formulas from iNSTRINSIC_vALUE_v3.xlsm to Python.
Implements 5 Fair Value methods + DuPont + Forecast metrics.
"""
import math


def safe_div(a, b, default=None):
    try:
        a = float(a)
        b = float(b)
        if b == 0:
            return default
        return a / b
    except (TypeError, ValueError):
        return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# 1. DCF Fair Value (Discounted Cash Flow)
# --------------------------------------------------------------------------
def calc_fair_value_dcf(
    revenue,           # Latest annual revenue (MB)
    ebit_margin,       # EBIT margin as decimal (e.g. 0.15)
    tax_rate,          # Effective tax rate decimal (e.g. 0.20)
    da_ratio,          # D&A as % of revenue (e.g. 0.05)
    capex_ratio,       # Capex as % of revenue (e.g. 0.06)
    nwc_ratio,         # Change in NWC as % of revenue (e.g. 0.02)
    sale_growth_y1_5,  # Sale growth % years 1-5 (user input, decimal)
    sale_growth_y6_10, # Sale growth % years 6-10 (default 2%)
    wacc,              # WACC decimal (e.g. 0.10)
    g_terminal,        # Terminal growth rate decimal (e.g. 0.03)
    shares_m,          # Shares outstanding (Millions)
    net_debt,          # Net Debt (MB) — to subtract from Enterprise Value
):
    """
    10-year FCF projection. Terminal value at year 10.
    Returns: Fair Value per share (THB)
    """
    try:
        revenue = safe_float(revenue)
        ebit_margin = safe_float(ebit_margin)
        tax_rate = safe_float(tax_rate, 0.20)
        da_ratio = safe_float(da_ratio, 0.05)
        capex_ratio = safe_float(capex_ratio, 0.06)
        nwc_ratio = safe_float(nwc_ratio, 0.02)
        sale_growth_y1_5 = safe_float(sale_growth_y1_5)
        sale_growth_y6_10 = safe_float(sale_growth_y6_10, 0.02)
        wacc = safe_float(wacc, 0.10)
        g_terminal = safe_float(g_terminal, 0.03)
        shares_m = safe_float(shares_m)
        net_debt = safe_float(net_debt)

        if shares_m <= 0 or revenue <= 0:
            return None

        total_pv = 0.0
        curr_revenue = revenue

        for yr in range(1, 11):
            g = sale_growth_y1_5 if yr <= 5 else sale_growth_y6_10
            curr_revenue *= (1 + g)
            ebit = curr_revenue * ebit_margin
            nopat = ebit * (1 - tax_rate)
            da = curr_revenue * da_ratio
            capex = curr_revenue * capex_ratio
            delta_nwc = curr_revenue * nwc_ratio
            fcf = nopat + da - capex - delta_nwc
            total_pv += fcf / ((1 + wacc) ** yr)

        # Terminal value
        terminal_fcf = curr_revenue * ebit_margin * (1 - tax_rate) * (1 + g_terminal)
        terminal_value = terminal_fcf / (wacc - g_terminal)
        pv_terminal = terminal_value / ((1 + wacc) ** 10)

        enterprise_value = total_pv + pv_terminal
        equity_value = enterprise_value - net_debt
        fair_value = equity_value / shares_m  # MB / M shares = THB/share

        return round(fair_value, 2) if fair_value > 0 else None

    except Exception:
        return None


# --------------------------------------------------------------------------
# 2. Constant Dividend (Gordon Growth Model)
# --------------------------------------------------------------------------
def calc_fair_value_div(dps, required_return, g=0.03):
    """
    FV_DIV = DPS / (r - g)
    Only valid for cash dividends.
    """
    try:
        dps = safe_float(dps)
        r = safe_float(required_return)
        g = safe_float(g)
        if r <= g or dps <= 0:
            return None
        return round(dps / (r - g), 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 3. DDM – 10-Year Dividend Discount Model
# --------------------------------------------------------------------------
def calc_fair_value_ddm(dps, dps_growth, required_return, g_terminal=0.03, years=10):
    """
    Projects DPS for `years`, discounts back, adds terminal value.
    """
    try:
        dps = safe_float(dps)
        g_growth = safe_float(dps_growth)
        r = safe_float(required_return)
        g_t = safe_float(g_terminal)
        if dps <= 0 or r <= g_t:
            return None

        total_pv = 0.0
        curr_dps = dps
        for yr in range(1, years + 1):
            curr_dps *= (1 + g_growth)
            total_pv += curr_dps / ((1 + r) ** yr)

        # Terminal value at year 10
        terminal_dps = curr_dps * (1 + g_t)
        terminal_value = terminal_dps / (r - g_t)
        pv_terminal = terminal_value / ((1 + r) ** years)

        return round(total_pv + pv_terminal, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 4. PER Method
# --------------------------------------------------------------------------
def calc_fair_value_per(eps, pe_benchmark):
    """FV_PER = EPS × Benchmark P/E"""
    try:
        eps = safe_float(eps)
        pe = safe_float(pe_benchmark)
        if eps <= 0 or pe <= 0:
            return None
        return round(eps * pe, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 5. PBV Method
# --------------------------------------------------------------------------
def calc_fair_value_pbv(book_value_per_share, pbv_benchmark):
    """FV_PBV = Book Value per Share × Benchmark P/BV"""
    try:
        bv = safe_float(book_value_per_share)
        pbv = safe_float(pbv_benchmark)
        if bv <= 0 or pbv <= 0:
            return None
        return round(bv * pbv, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Sensitivity Analysis (DCF with grid of sale growth & terminal g)
# --------------------------------------------------------------------------
def calc_sensitivity(
    revenue, ebit_margin, tax_rate, da_ratio, capex_ratio, nwc_ratio,
    wacc, shares_m, net_debt,
    sale_growth_range=None, g_terminal_range=None
):
    """
    Returns a 2D dict of {sale_growth: {g_terminal: fair_value}}
    sale_growth_range: list of decimals [0.01..0.10]
    g_terminal_range: list of decimals [0.03..0.07]
    """
    if sale_growth_range is None:
        sale_growth_range = [i / 100 for i in range(1, 11)]
    if g_terminal_range is None:
        g_terminal_range = [i / 100 for i in range(3, 8)]

    results = {}
    for sg in sale_growth_range:
        results[round(sg * 100, 0)] = {}
        for g in g_terminal_range:
            fv = calc_fair_value_dcf(
                revenue, ebit_margin, tax_rate, da_ratio, capex_ratio,
                nwc_ratio, sg, 0.02, wacc, g, shares_m, net_debt
            )
            results[round(sg * 100, 0)][round(g * 100, 0)] = fv

    # Find min/max across grid
    all_vals = [v for row in results.values() for v in row.values() if v is not None]
    min_val = round(min(all_vals), 2) if all_vals else None
    max_val = round(max(all_vals), 2) if all_vals else None
    return results, min_val, max_val


# --------------------------------------------------------------------------
# Forecast / Growth Metrics (from VBA Valuation_Button_Click)
# --------------------------------------------------------------------------
def calc_forecast_metrics(
    curr_eps,              # Most recent quarter EPS
    annual_eps,            # Latest TTM EPS (used for Q4 Actuals)
    prev_year_annual_eps,  # Exact annual EPS of the previous year
    pe,                    # Current P/E
    avg_payout,            # Average payout ratio (decimal)
    current_price,         # Current market price
    multiplier=1,          # Quarter multiplier (Q1=4, Q2=2, Q3=1.33, Q4=1)
):
    """
    Returns dict with forecast values matching VBA logic, correctly distinguishing
    between Full Year Actuals (Q4) and Intra-Year Forecasts (Q1-Q3).
    """
    out = {}
    try:
        curr_eps = safe_float(curr_eps)
        annual_eps = safe_float(annual_eps)
        prev_year_annual_eps = safe_float(prev_year_annual_eps) if prev_year_annual_eps is not None else None
        pe = safe_float(pe)
        avg_payout = safe_float(avg_payout)
        current_price = safe_float(current_price)
        multiplier = safe_float(multiplier, 1)

        if multiplier == 1.0:
            # Q4: We have the Actual Annual EPS (Sum of Q1+Q2+Q3+Q4)
            base_eps = annual_eps
            is_forecast = False
        else:
            # Q1-Q3: We Forecast the Annual EPS
            base_eps = curr_eps * multiplier
            is_forecast = True

        # YoY EPS Growth (compared to the true Annual EPS of the previous year)
        if prev_year_annual_eps and prev_year_annual_eps != 0:
            yoy_eps_growth = ((base_eps - prev_year_annual_eps) / abs(prev_year_annual_eps)) * 100
        else:
            yoy_eps_growth = 0.0

        forecast_eps = base_eps

        # Forecast Price = Forecast EPS × P/E
        forecast_price = base_eps * pe

        # Margin of Safety (forecast vs current)
        forecast_price_margin = safe_div(forecast_price - current_price, current_price, 0) * 100

        # Forecast DPS = Avg Payout × Curr EPS × Quarter Multiplier
        forecast_dps = avg_payout * curr_eps * multiplier

        # Forecast Yield
        forecast_yield = safe_div(forecast_dps, current_price, 0) * 100

        # PEG (requires eps_growth_pct as net profit growth)
        peg = safe_div(pe, yoy_eps_growth) if yoy_eps_growth and yoy_eps_growth > 0 else None

        out = {
            "is_forecast": is_forecast,
            "yoy_eps_growth": round(yoy_eps_growth, 2),
            "forecast_eps": round(forecast_eps, 2),
            "forecast_price": round(forecast_price, 2),
            "forecast_price_margin": round(forecast_price_margin, 2),
            "forecast_dps": round(forecast_dps, 4),
            "forecast_yield": round(forecast_yield, 2),
            "peg": round(peg, 2) if peg else None,
        }
    except Exception as e:
        out["error"] = str(e)
    return out


# --------------------------------------------------------------------------
# DuPont Analysis
# --------------------------------------------------------------------------
def calc_dupont(npm, asset_turnover, financial_leverage):
    """ROE = NPM × Asset Turnover × Financial Leverage"""
    try:
        npm = safe_float(npm)
        at = safe_float(asset_turnover)
        fl = safe_float(financial_leverage)
        roe = npm * at * fl
        return round(roe, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Margin of Safety
# --------------------------------------------------------------------------
def calc_margin_of_safety(fair_value, current_price):
    """MOS = (FV - Price) / Price × 100"""
    try:
        fv = safe_float(fair_value)
        p = safe_float(current_price)
        if p <= 0:
            return None
        return round((fv - p) / p * 100, 2)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Color Rating Helper (from VBA color rules)
# --------------------------------------------------------------------------
CRITERIA = {
    "npm":       [(10, "green"), (5,  "yellow"), (0,  "red")],
    "roe":       [(20, "green"), (10, "yellow"), (0,  "red")],
    "sale_growth": [(10, "green"), (1,  "yellow"), (None, "red")],
    "eps_growth":  [(7,  "green"), (1,  "yellow"), (None, "red")],
    "yield":     [(5,  "green"), (1,  "yellow"), (None, "red")],
    "rotc":      [(20, "green"), (10, "yellow"), (0,  "red")],
    "roic":      [(20, "green"), (10, "yellow"), (0,  "red")],
}

def get_color(metric, value):
    """Returns 'green', 'yellow', or 'red' for a given metric value."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "gray"

    if metric == "de":
        return "green" if v < 1 else "red"
    if metric == "pe":
        if 0 < v < 15: return "green"
        if 15 <= v < 40: return "yellow"
        return "red"
    if metric == "peg":
        if 0 < v < 0.75: return "green"
        return "red"
    if metric == "pbv":
        if v < 1: return "green"
        if v < 2: return "yellow"
        return "red"
    if metric == "ps":
        if v < 16: return "green"
        if v < 40: return "yellow"
        return "red"
    if metric == "mktcap_rev":
        if v < 1.5: return "green"
        if v < 3: return "yellow"
        return "red"
    if metric == "asset_equity":
        return "green" if v < 2 else "red"
    if metric == "asset_turnover":
        return "green" if v > 1 else "red"

    # Threshold-based metrics
    if metric in CRITERIA:
        for threshold, color in CRITERIA[metric]:
            if threshold is None or v >= threshold:
                return color

    return "gray"


# --------------------------------------------------------------------------
# BANKING / FINANCE SECTOR – Sector-Specific Valuation Models
#
# Banks and leasing/finance companies (BBL, ASK, etc.) cannot be valued with
# the standard DCF model because their "revenue" = interest income and there
# is no typical EBIT margin on sales.  The VBA dispatches to sector-specific
# logic that skips Cash Cycle and suppresses GPM.
#
# Correct methods for banking/finance stocks:
#   1. Justified P/BV  (H. Damodaran — primary method for banks)
#   2. Gordon Growth DDM  (Constant Dividend model using sustainable g)
#   3. P/E Method  (same formula, lower sector benchmark: SET banks ~8-12x)
#   4. P/BV Method  (Book Value × benchmark P/BV)
#   5. DCF → N/A (not computed; returns None with explanation)
# --------------------------------------------------------------------------

def calc_fair_value_justified_pbv(book_value_per_share, roe_pct,
                                   cost_of_equity, g_terminal=0.03):
    """
    Justified P/BV for banks (Damodaran):
      Justified_PBV = (ROE − g) / (COE − g)
      Fair Value    = Justified_PBV × Book Value per Share

    Args:
        book_value_per_share : BV/share in THB  (e.g. 302.76 for BBL)
        roe_pct              : ROE in percent    (e.g.   7.82 for BBL)
        cost_of_equity       : COE as decimal    (e.g.   0.09)
        g_terminal           : Sustainable growth as decimal (e.g. 0.03)
    Returns:
        Fair value per share (THB), or None if inputs invalid.
    """
    try:
        bv   = safe_float(book_value_per_share)
        roe  = safe_float(roe_pct) / 100   # % → decimal
        coe  = safe_float(cost_of_equity)
        g    = safe_float(g_terminal)

        if bv <= 0 or coe <= g:
            return None

        justified_pbv = (roe - g) / (coe - g)
        if justified_pbv <= 0:
            return None

        return round(bv * justified_pbv, 2)

    except Exception:
        return None


def calc_fair_value_gordon_ddm(dps, roe_pct, payout_pct,
                                cost_of_equity, g_override=None):
    """
    Gordon Growth DDM for banks:
      Sustainable g = ROE × (1 − Payout Ratio)
      Fair Value    = DPS / (COE − g)

    This is the "Constant Dividend" method from the VBA but with a
    sustainable growth rate derived from ROE × retention ratio,
    which is more appropriate than a fixed user-supplied g for banks.

    Args:
        dps           : Annual DPS in THB
        roe_pct       : ROE in percent
        payout_pct    : Payout ratio in percent  (e.g. 50.0)
        cost_of_equity: COE as decimal
        g_override    : Optional fixed g (decimal); skips ROE-based calc
    Returns:
        Fair value per share (THB), or None if invalid.
    """
    try:
        dps    = safe_float(dps)
        roe    = safe_float(roe_pct) / 100
        payout = safe_float(payout_pct) / 100
        coe    = safe_float(cost_of_equity)

        if dps <= 0:
            return None

        if g_override is not None:
            g = safe_float(g_override)
        else:
            # Sustainable growth rate
            retention = 1 - payout
            g = roe * retention
            g = max(0.0, min(g, 0.08))   # cap: 0% – 8%

        if coe <= g:
            return None

        return round(dps / (coe - g), 2)

    except Exception:
        return None


def build_bank_valuation(price, bv_per_share, roe_pct, eps, dps,
                          payout_pct, cost_of_equity,
                          pe_benchmark, pbv_benchmark,
                          g_terminal=0.03):
    """
    Full banking / finance sector valuation package.
    Returns a dict that mirrors the structure used in app.py.

    Mapping to UI labels:
      fv_dcf  →  N/A   (DCF not applicable)
      fv_div  →  GORDON DDM   (sustainable-g Constant Dividend)
      fv_ddm  →  JUSTIFIED P/BV  (primary bank method)
      fv_per  →  P/E Method
      fv_pbv  →  P/BV × Benchmark
    """
    fv_justified_pbv = calc_fair_value_justified_pbv(
        bv_per_share, roe_pct, cost_of_equity, g_terminal
    )
    fv_gordon = calc_fair_value_gordon_ddm(
        dps, roe_pct, payout_pct, cost_of_equity
    )
    fv_per = calc_fair_value_per(eps, pe_benchmark)
    fv_pbv = calc_fair_value_pbv(bv_per_share, pbv_benchmark)

    return {
        "fv_dcf":     None,              # N/A for banks
        "fv_div":     fv_gordon,         # Gordon DDM = Constant Dividend
        "fv_ddm":     fv_justified_pbv,  # Justified P/BV (key bank metric)
        "fv_per":     fv_per,
        "fv_pbv":     fv_pbv,
        "dcf_note":   "DCF N/A for Banking/Finance — DCF requires operating FCF",
        "ddm_label":  "JUSTIFIED P/BV",  # Override UI label
        "div_label":  "GORDON DDM",      # Override UI label
    }
