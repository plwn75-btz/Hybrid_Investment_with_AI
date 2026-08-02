"""
app.py  (v2 – fixed DuPont, ROE%, banking/finance sector models)
-----------------------------------------------------------------
Flask web server for the Intrinsic Valuation tool.
Converts iNSTRINSIC_vALUE_v3.xlsm + VBA_Code_02052026 to Python.
"""
import logging
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps

from data_fetcher import get_yf_data, get_bond_yield, get_bond_yield_source, determine_sector_type, get_momentum_data, get_historical_ohlcv
from news_fetcher import get_all_news
from valuation_engine import (
    calc_fair_value_dcf,
    calc_fair_value_div,
    calc_fair_value_ddm,
    calc_fair_value_per,
    calc_fair_value_pbv,
    calc_sensitivity,
    calc_forecast_metrics,
    calc_dupont,
    calc_margin_of_safety,
    get_color,
    safe_float,
    build_bank_valuation,
)

from screening_api import screening_bp
from screening_engine import get_default_date

import json
import os
import sys
import requests

# Security Configuration
APP_PASSWORD = os.environ.get("APP_PASSWORD", "btz2026") # Default fallback

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_base_path():
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

from datetime import timedelta

# Setup Flask with explicit template and static paths for Cloud & Local robustness
template_dir = os.path.join(BASE_PATH, 'templates')
static_dir = os.path.join(BASE_PATH, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.register_blueprint(screening_bp)
app.secret_key = os.environ.get("SECRET_KEY", "btzi-intrinsic-valuation-2024")
app.permanent_session_lifetime = timedelta(hours=1)

@app.errorhandler(500)
def handle_internal_server_error(e):
    return "Internal Server Error. Please contact admin or try again later.", 500

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        else:
            error = "Invalid password. Please try again."
    try:
        return render_template("login.html", error=error)
    except Exception as e:
        err_msg = f'<div style="color:#ef4444;margin-top:10px;font-size:0.85rem;">{error}</div>' if error else ''
        return f'''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Login - Hybrid Investment</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
            <style>
                body {{ font-family: 'Inter', sans-serif; background-color: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .login-card {{ background: #1e293b; padding: 2.5rem; border-radius: 1rem; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5); width: 100%; max-width: 400px; text-align: center; }}
                h1 {{ font-weight: 600; margin-bottom: 0.5rem; color: #fff; }}
                p {{ color: #94a3b8; margin-bottom: 2rem; font-size: 0.9rem; }}
                input {{ width: 100%; padding: 0.8rem; margin-bottom: 1.5rem; border-radius: 0.5rem; border: 1px solid #334155; background: #0f172a; color: #fff; box-sizing: border-box; font-size: 1rem; }}
                button {{ width: 100%; padding: 0.8rem; border-radius: 0.5rem; border: none; background: #6366f1; color: #fff; font-weight: 600; cursor: pointer; }}
                button:hover {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <div class="login-card">
                <h1>Welcome Back</h1>
                <p>Please enter the access password</p>
                <form method="POST">
                    <input type="password" name="password" placeholder="Password" required autofocus>
                    <button type="submit">Unlock System</button>
                </form>
                {err_msg}
            </div>
        </body>
        </html>
        '''

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Determine where to save the shortlist (persist in EXE folder, GitHub Gist, or Local)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
    SHORTLIST_FILE = os.path.join(EXE_DIR, "shortlist.json")
else:
    SHORTLIST_FILE = os.path.join(BASE_PATH, "shortlist.json")

# In-memory short list
short_list = []

def load_shortlist():
    global short_list
    if GITHUB_TOKEN and GIST_ID:
        try:
            url = f"https://api.github.com/gists/{GIST_ID}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                gist_data = resp.json()
                file_data = gist_data.get("files", {}).get("shortlist.json", {})
                content = file_data.get("content")
                if content:
                    data = json.loads(content)
                    if isinstance(data, list):
                        short_list = data
                        logger.info("Shortlist loaded from GitHub Gist.")
                        return
                    else:
                        logger.error(f"Gist content is not a list: {type(data)}")
            else:
                logger.error(f"Gist Load Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Gist Load Exception: {e}")

    # Fallback to local
    if os.path.exists(SHORTLIST_FILE):
        try:
            with open(SHORTLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    short_list = data
                    logger.info("Shortlist loaded from local storage.")
                else:
                    logger.error(f"Local shortlist file is not a list: {type(data)}")
        except Exception as e:
            logger.error(f"Local Load Error: {e}")
    
    # Final safeguard
    if not isinstance(short_list, list):
        logger.warning("Shortlist was not a list after loading. Initializing to empty list.")
        short_list = []

def save_shortlist():
    if GITHUB_TOKEN and GIST_ID:
        try:
            url = f"https://api.github.com/gists/{GIST_ID}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            payload = {
                "files": {
                    "shortlist.json": {
                        "content": json.dumps(short_list, ensure_ascii=False, indent=2)
                    }
                }
            }
            resp = requests.patch(url, headers=headers, json=payload, timeout=3)
            if resp.status_code == 200:
                logger.info("Shortlist saved to GitHub Gist.")
            else:
                logger.error(f"Gist Save Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Gist Save Exception: {e}")
    
    # Also save locally as a backup/for standalone mode
    try:
        with open(SHORTLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(short_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save local shortlist: {e}")

# Initial load
load_shortlist()


@app.route("/")
@login_required
def index():
    try:
        raw_yield = get_bond_yield()
        bond_yield_pct = round(raw_yield * 100, 3) if raw_yield is not None else 2.199
    except Exception as e:
        logger.error(f"Error calculating bond yield for index: {e}")
        bond_yield_pct = 2.199
        
    bond_source = get_bond_yield_source()
    default_date = str(get_default_date())
    return render_template("index.html", bond_yield_default=bond_yield_pct, bond_yield_source=bond_source, default_date=default_date)


@app.route("/api/valuate", methods=["POST"])
def valuate():
    """
    Main valuation API.  Dispatches between industrial and banking/finance
    sector models exactly as the VBA Valuation_Button_Click does.
    """
    data = request.json or {}
    symbol          = (data.get("symbol") or "").strip().upper()
    sale_growth_pct = safe_float(data.get("sale_growth",    5.0))
    bond_yield_pct  = safe_float(data.get("bond_yield",     round(get_bond_yield() * 100, 3)))
    per_benchmark   = safe_float(data.get("per_benchmark", 15.0))
    pbv_benchmark   = safe_float(data.get("pbv_benchmark",  1.5))

    if not symbol:
        return jsonify({"error": "Please enter a stock symbol."}), 400

    logger.info(f"Valuation: {symbol} | SaleGrowth={sale_growth_pct}% | Bond={bond_yield_pct}%")

    # ── 1. Fetch market data ──────────────────────────────────────────────
    mkt = get_yf_data(symbol)
    if mkt.get("error"):
        return jsonify({"error": mkt["error"]}), 404

    # ── 2. Extract raw values ─────────────────────────────────────────────
    price         = safe_float(mkt.get("price"))
    hi52          = mkt.get("hi_52wk")
    lo52          = mkt.get("lo_52wk")
    eps           = safe_float(mkt.get("eps"))
    pe            = safe_float(mkt.get("pe"))
    pbv           = safe_float(mkt.get("pbv"))
    bv_ps         = safe_float(mkt.get("bv_per_share"))
    dps           = safe_float(mkt.get("dps"))

    # All these are already in % from data_fetcher
    roe           = safe_float(mkt.get("roe"))   # e.g. 7.82
    roa           = safe_float(mkt.get("roa"))
    npm           = safe_float(mkt.get("npm"))
    gpm           = safe_float(mkt.get("gpm"))
    payout_pct    = safe_float(mkt.get("payout")) or 50.0    # % (e.g. 69.8)
    ebit_margin_pct = safe_float(mkt.get("ebit_margin")) or 10.0

    de            = mkt.get("de")
    peg           = mkt.get("peg")
    revenue_m     = safe_float(mkt.get("revenue_m"))
    net_debt_m    = safe_float(mkt.get("net_debt_m"))
    shares_m      = safe_float(mkt.get("shares_m"))
    ebitda        = mkt.get("ebitda_m")
    ev            = mkt.get("ev_m")
    ev_ebitda     = mkt.get("ev_ebitda")
    ps            = mkt.get("ps")
    mktcap_rev    = mkt.get("mktcap_rev")

    # DuPont components (now correctly fetched from balance sheet)
    asset_to      = mkt.get("asset_turnover")      # e.g. 0.35
    fin_lev       = mkt.get("financial_leverage")  # e.g. 4.2

    # ── 3. WACC / Cost of equity ──────────────────────────────────────────
    rf                  = bond_yield_pct / 100
    equity_risk_premium = 0.06    # market ERP assumption
    beta                = mkt.get("beta") or 1.0     # fetched from yf
    cost_of_equity      = rf + beta * equity_risk_premium   # CAPM
    
    # Calculate WACC dynamically based on capital structure
    E_val = mkt.get("market_cap_m") or 1
    D_val = mkt.get("total_debt_m") or 0
    V_val = E_val + D_val
    if V_val > 0:
        cost_of_debt = rf + 0.02  # estimate 2% spread
        tax_rate_est = 0.20
        wacc = (E_val / V_val) * cost_of_equity + (D_val / V_val) * cost_of_debt * (1 - tax_rate_est)
    else:
        wacc = cost_of_equity

    sale_growth         = sale_growth_pct / 100
    ebit_margin_dec     = ebit_margin_pct / 100

    # ── 4. Sector detection ───────────────────────────────────────────────
    sector_raw    = mkt.get("sector", "")
    industry_raw  = mkt.get("industry", "")
    sector_type   = determine_sector_type(sector_raw, industry_raw)
    is_financial  = sector_type in ("banking", "finance")

    # ── 5. Run valuation models (sector-aware) ────────────────────────────
    fv_labels = {}    # Optional UI label overrides

    if is_financial:
        # --- Banking / Finance sector ---
        # Primary: Justified P/BV + Gordon DDM  (VBA sector dispatch)
        bank_vals = build_bank_valuation(
            price       = price,
            bv_per_share= bv_ps,
            roe_pct     = roe,
            eps         = eps,
            dps         = dps,
            payout_pct  = payout_pct,
            cost_of_equity = cost_of_equity,
            pe_benchmark= per_benchmark,
            pbv_benchmark= pbv_benchmark,
            g_terminal  = 0.03,
        )
        fv_dcf = bank_vals["fv_dcf"]   # None
        fv_div = bank_vals["fv_div"]   # Gordon DDM
        fv_ddm = bank_vals["fv_ddm"]   # Justified P/BV
        fv_per = bank_vals["fv_per"]
        fv_pbv = bank_vals["fv_pbv"]
        fv_labels = {
            "dcf": "N/A (Banking)",
            "div": bank_vals.get("div_label", "GORDON DDM"),
            "ddm": bank_vals.get("ddm_label", "JUSTIFIED P/BV"),
        }
        sens_min, sens_max = None, None   # Sensitivity not applicable to banks

    else:
        # --- Industrial / Standard sector ---
        fv_dcf = calc_fair_value_dcf(
            revenue         = revenue_m,
            ebit_margin     = ebit_margin_dec,
            tax_rate        = 0.20,
            da_ratio        = 0.05,
            capex_ratio     = 0.06,
            nwc_ratio       = 0.02,
            sale_growth_y1_5  = sale_growth,
            sale_growth_y6_10 = 0.02,
            wacc            = wacc,
            g_terminal      = 0.03,
            shares_m        = shares_m,
            net_debt        = net_debt_m,
        )

        # Sensitivity (sale growth 1-10%, terminal g 3-7%)
        sens_min, sens_max = None, None
        try:
            _, sens_min, sens_max = calc_sensitivity(
                revenue_m, ebit_margin_dec, 0.20, 0.05, 0.06, 0.02,
                wacc, shares_m, net_debt_m
            )
        except Exception:
            pass

        # Constant Dividend (Gordon Growth)
        g_div  = min(sale_growth, 0.05)
        fv_div = calc_fair_value_div(dps, cost_of_equity, g_div) if dps > 0 else None

        # 10-year DDM
        dps_growth = sale_growth * 0.8
        fv_ddm = calc_fair_value_ddm(dps, dps_growth, cost_of_equity, 0.03) if dps > 0 else None

        fv_per = calc_fair_value_per(eps, per_benchmark)
        fv_pbv = calc_fair_value_pbv(bv_ps, pbv_benchmark)

    # ── 6. Forecast metrics ───────────────────────────────────────────────
    hist        = mkt.get("hist_eps") or {}
    curr_q_eps  = hist.get("curr_q_eps")
    ttm_eps     = hist.get("ttm_eps") or eps
    prev_year_annual_eps = hist.get("prev_year_annual_eps")
    multiplier  = hist.get("multiplier", 1)  # use detected multiplier
    q_label     = hist.get("q_label", "Annual")

    # Use trailing EPS as fallback ONLY if quarterly is missing
    if curr_q_eps is None:
        curr_q_eps = eps

    # When Q4 (full year reported), prefer the audited annual EPS from
    # financial_history over the quarterly TTM sum.  This ensures the
    # Highlight Box EPS matches the EPS History Chart bar exactly.
    # GUARD: Only override if the chart's latest year matches the reported
    # quarter's year — prevents using stale annual data when yfinance has
    # Q4 quarterly data for a new year but annual financials lag behind.
    if multiplier == 1.0 and mkt.get("financial_history"):
        latest_fh = mkt["financial_history"][-1]
        q_year_str = q_label.split()[-1] if q_label else ""
        chart_year_str = str(latest_fh.get("year", ""))
        if q_year_str == chart_year_str:
            annual_eps_from_chart = latest_fh.get("eps")
            if annual_eps_from_chart is not None:
                ttm_eps = round(annual_eps_from_chart, 2)

    forecast = calc_forecast_metrics(
        curr_eps      = curr_q_eps,
        annual_eps    = ttm_eps,
        prev_year_annual_eps = prev_year_annual_eps,
        pe            = pe,
        avg_payout    = payout_pct / 100,   # convert % → decimal for function
        current_price = price,
        multiplier    = multiplier,
    )

    # ── 7. DuPont Analysis ────────────────────────────────────────────────
    # npm as decimal for DuPont formula
    npm_dec = (npm or 0) / 100
    dupont_roe_dec = calc_dupont(npm_dec, asset_to or 1, fin_lev or 1)
    # Convert to percentage for display
    dupont_roe_pct = round(dupont_roe_dec * 100, 2) if dupont_roe_dec is not None else None

    # ── 8. Margins of Safety ─────────────────────────────────────────────
    mos_dcf = calc_margin_of_safety(fv_dcf, price) if fv_dcf else None
    mos_div = calc_margin_of_safety(fv_div, price) if fv_div else None
    mos_ddm = calc_margin_of_safety(fv_ddm, price) if fv_ddm else None
    mos_per = calc_margin_of_safety(fv_per, price) if fv_per else None
    mos_pbv = calc_margin_of_safety(fv_pbv, price) if fv_pbv else None

    # ── 9. Color ratings (VBA rules) ──────────────────────────────────────
    colors = {
        "npm":            get_color("npm",          npm or 0),
        "roe":            get_color("roe",          roe or 0),
        "de":             get_color("de",           safe_float(de) if de else 0),
        "sale_growth":    get_color("sale_growth",  sale_growth_pct),
        "eps_growth":     get_color("eps_growth",   forecast.get("yoy_eps_growth", 0) or 0),
        "pe":             get_color("pe",           pe or 0),
        "yield":          get_color("yield",        forecast.get("forecast_yield", 0) or 0),
        "peg":            get_color("peg",          safe_float(peg) if peg else 0),
        "pbv":            get_color("pbv",          pbv or 0),
        "ps":             get_color("ps",           safe_float(ps) if ps else 0),
        "mktcap_rev":     get_color("mktcap_rev",   safe_float(mktcap_rev) if mktcap_rev else 0),
        "rotc":           get_color("rotc",         roa or 0),
        "roic":           get_color("roic",         roe or 0),
        "asset_equity":   get_color("asset_equity", safe_float(fin_lev) if fin_lev else 0),
        "asset_turnover": get_color("asset_turnover", safe_float(asset_to) if asset_to else 0),
    }

    # ── 10. Highlight narrative ───────────────────────────────────────────
    def _s(v, fmt=".2f", default="N/A"):
        if v is None: return default
        try: return format(float(v), fmt)
        except: return default

    yoy_g   = forecast.get("yoy_eps_growth") or 0
    f_eps   = forecast.get("forecast_eps")   or 0
    f_price = forecast.get("forecast_price") or 0
    f_pm    = forecast.get("forecast_price_margin") or 0
    f_dps   = forecast.get("forecast_dps")   or 0
    f_yield = forecast.get("forecast_yield") or 0
    f_peg   = forecast.get("peg")
    is_forecast = forecast.get("is_forecast", True)

    div_yield_disp = mkt.get("dividend_yield")
    if div_yield_disp and div_yield_disp > 100:
        div_yield_disp = div_yield_disp / 100

    non_cash_note = ""
    if payout_pct and payout_pct > 150:
        non_cash_note = " *Note: High payout may indicate non-cash/stock dividend."

    if is_financial:
        sector_note = f"[{sector_type.upper()} SECTOR: DCF N/A — using Justified P/BV & Gordon DDM] "
    else:
        sector_note = ""

    label_prefix = "Forecast Annual EPS" if is_forecast else "Reported Annual EPS"

    highlight = (
        f"{sector_note}[{q_label}] "
        f"{label_prefix} is {_s(f_eps)} @ {_s(yoy_g, '.1f')}% YOY Growth "
        f"and current P/E {_s(pe, '.1f')}. "
        f"Forecast Price is {_s(f_price)} THB with MOS {_s(f_pm, '.1f')}%. "
        f"PEG is {_s(f_peg)} and Forecast DPS @Year-End is "
        f"{_s(f_dps, '.2f')} THB/Share with Yield {_s(f_yield, '.2f')}%."
    )

    # ── 11. Build response ────────────────────────────────────────────────
    result = {
        # Company info
        "symbol":         symbol,
        "company_name":   mkt.get("company_name"),
        "company_full":   mkt.get("company_full"),
        "sector":         sector_raw,
        "industry":       industry_raw,
        "sector_type":    sector_type,
        "is_financial":   is_financial,
        "website":        mkt.get("website"),
        "last_xd_date":   mkt.get("last_xd_date"),
        "upcoming_xd_date": mkt.get("upcoming_xd_date"),
        "financial_history": mkt.get("financial_history"),
        "quarterly_history": mkt.get("quarterly_history"),
        # Price
        "price":   price,
        "hi_52wk": hi52,
        "lo_52wk": lo52,
        # Fair values
        "fv_dcf":  fv_dcf,
        "fv_div":  fv_div,
        "fv_ddm":  fv_ddm,
        "fv_per":  fv_per,
        "fv_pbv":  fv_pbv,
        "fv_labels": fv_labels,
        # Sensitivity
        "sens_min": sens_min,
        "sens_max": sens_max,
        # MOS
        "mos_dcf": mos_dcf,
        "mos_div": mos_div,
        "mos_ddm": mos_ddm,
        "mos_per": mos_per,
        "mos_pbv": mos_pbv,
        # Forecast
        "forecast": forecast,
        "q_label":  q_label,
        # Key metrics (all percentages already in %)
        "eps":        eps,
        "dps":        dps,
        "pe":         pe,
        "pbv":        pbv,
        "peg":        peg,
        "roe":        roe,         # % (e.g. 7.82)
        "roa":        roa,         # %
        "npm":        npm,         # %
        "gpm":        gpm,         # %
        "de":         de,
        "payout":     payout_pct,  # %
        "sale_growth_pct": sale_growth_pct,
        "ebit_margin":     ebit_margin_pct,
        "ebitda":     ebitda,
        "ev":         ev,
        "ev_ebitda":  ev_ebitda,
        "asset_turnover":    asset_to,
        "financial_leverage": fin_lev,
        "bv_per_share": bv_ps,
        "ps":           ps,
        "mktcap_rev":   mktcap_rev,
        "shares_m":     shares_m,
        "market_cap_m": mkt.get("market_cap_m"),
        # DuPont — npm in %, turnover as ratio, leverage as ratio, ROE in %
        "dupont": {
            "npm_pct":            round(npm or 0, 2),          # display as %
            "npm_dec":            round((npm or 0) / 100, 4),  # for formula
            "asset_turnover":     asset_to,
            "financial_leverage": fin_lev,
            "roe_pct":            dupont_roe_pct,              # in % ← FIXED
        },
        # Colors
        "colors":   colors,
        # Narrative
        "highlight":       highlight,
        "dividend_policy": (
            f"Payout Ratio: {_s(payout_pct, '.1f')}%  |  DPS: {_s(dps, '.2f')} THB/share  |  "
            f"Div. Yield: {_s(div_yield_disp, '.2f')}%{non_cash_note}"
        ),
        "bond_yield_pct": bond_yield_pct,
        "bond_yield_source": get_bond_yield_source(),
        "wacc_pct":       round(wacc * 100, 2),
        "coe_pct":        round(cost_of_equity * 100, 2),
    }
    return jsonify(result)


# ---------------------------------------------------------------------------
# Short List endpoints
# ---------------------------------------------------------------------------
@app.route("/api/shortlist/add", methods=["POST"])
def shortlist_add():
    global short_list
    data = request.json
    if data:
        symbol = data.get("symbol", "Unknown")
        # Ensure short_list is a list
        if not isinstance(short_list, list):
            logger.warning("short_list was not a list during add! Fixing now.")
            short_list = []
            
        logger.info(f"Adding {symbol} to shortlist. Current count: {len(short_list)}")
        short_list.append(data)
        save_shortlist()
        logger.info(f"Successfully added {symbol}. New count: {len(short_list)}")
    else:
        logger.warning("Received empty data for shortlist addition.")
    return jsonify({"count": len(short_list), "items": short_list})


@app.route("/api/shortlist", methods=["GET"])
def shortlist_get():
    return jsonify({"items": short_list})


@app.route("/api/shortlist/clear", methods=["POST"])
def shortlist_clear():
    short_list.clear()
    save_shortlist()
    return jsonify({"count": 0})


@app.route("/api/shortlist/delete", methods=["POST"])
def shortlist_delete():
    """Delete a single item from the short list by index."""
    data = request.json or {}
    idx = data.get("index")
    if idx is not None and 0 <= idx < len(short_list):
        removed = short_list.pop(idx)
        save_shortlist()
        return jsonify({"count": len(short_list), "items": short_list,
                        "removed": removed.get("symbol", "")})
    return jsonify({"error": "Invalid index", "count": len(short_list), "items": short_list}), 400


@app.route("/api/bond_yield", methods=["GET"])
def bond_yield_api():
    y = get_bond_yield()
    return jsonify({"bond_yield_pct": round(y * 100, 3)})


# ---------------------------------------------------------------------------
# Momentum endpoint
# ---------------------------------------------------------------------------
@app.route("/api/momentum", methods=["POST"])
def momentum_api():
    """Fetch momentum/volume data for a stock."""
    data = request.json or {}
    symbol = (data.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Please enter a stock symbol."}), 400

    logger.info(f"Momentum: {symbol}")
    result = get_momentum_data(symbol)
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


# ---------------------------------------------------------------------------
# News endpoint
# ---------------------------------------------------------------------------
@app.route("/api/news", methods=["POST"])
def news_api():
    """Fetch aggregated news for a stock."""
    data = request.json or {}
    symbol = (data.get("symbol") or "").strip().upper()
    days = int(data.get("days", 15))
    if not symbol:
        return jsonify({"error": "Please enter a stock symbol."}), 400

    logger.info(f"News: {symbol} (last {days} days)")
    articles = get_all_news(symbol, days_back=days)
    sources = list(set(a.get("source", "").split(" (")[0] for a in articles))
    return jsonify({"articles": articles, "count": len(articles), "sources": sources})


# ---------------------------------------------------------------------------
# Historical Chart endpoint
# ---------------------------------------------------------------------------
@app.route("/api/historical_chart", methods=["POST"])
def historical_chart_api():
    """Fetch historical OHLCV data for technical charting."""
    data = request.json or {}
    symbol = (data.get("symbol") or "").strip().upper()
    period = data.get("period", "1y")
    if not symbol:
        return jsonify({"error": "Please enter a stock symbol."}), 400

    logger.info(f"Historical Chart: {symbol} ({period})")
    result = get_historical_ohlcv(symbol, period=period)
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import webbrowser, threading, time as _time

    # Use PORT from environment (Cloud) or default to 5101 (Local)
    PORT = int(os.environ.get("PORT", 5101))

    # Warm the bond yield cache at startup
    print("Fetching 10Y Thai Gov Bond Yield from ThaiBMA...")
    try:
        _yield = get_bond_yield()
        print(f"  -> 10Y Yield: {_yield*100:.4f}%")
    except Exception as e:
        print(f"  -> Failed to fetch bond yield: {e}")

    def _open():
        _time.sleep(1.5)
        try:
            webbrowser.open(f"http://localhost:{PORT}")
        except:
            pass

    # Only attempt to open browser if not in a cloud environment
    if "PORT" not in os.environ:
        threading.Thread(target=_open, daemon=True).start()

    print("=" * 60)
    print("  HYBRID INVESTMENT WEB APP (CLOUD-READY)")
    print("  BTZ Inc. Ver.5.0 2026  -  Python Edition")
    print(f"  Running on: http://0.0.0.0:{PORT}")
    print("=" * 60)
    
    # In production/cloud, use gunicorn. This block is for local testing.
    app.run(host="0.0.0.0", debug=True, port=PORT, use_reloader=False)
