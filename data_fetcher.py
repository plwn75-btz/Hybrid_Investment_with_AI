"""
data_fetcher.py  (v2 – fixed DuPont inputs + sector detection)
---------------------------------------------------------------
Fetches financial data for SET-listed stocks via yfinance (.BK).
Key fix: totalAssets, totalEquity fetched from balance_sheet (not info dict).
"""
import math
import logging
import os

logger = logging.getLogger(__name__)

_yf_session = None

def get_yf_session():
    global _yf_session
    if _yf_session is not None:
        return _yf_session

    try:
        from curl_cffi import requests as cffi_requests
        _yf_session = cffi_requests.Session(impersonate="chrome")
    except Exception as e:
        logger.warning(f"curl_cffi session setup failed ({e}). Letting yfinance handle session natively.")
        _yf_session = None

    return _yf_session



def get_yf_data(symbol: str) -> dict:
    """
    Fetch data from yfinance.  Tries SYMBOL.BK first, then bare SYMBOL.
    Returns a rich dict of financial metrics including DuPont components.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance not installed. Run: pip install yfinance"}

    # Remove accidental .BK suffix before adding it back
    symbol_clean = symbol.upper().removesuffix(".BK")
    for ticker_str in [f"{symbol_clean}.BK", symbol_clean]:
        try:
            session = get_yf_session()
            ticker = yf.Ticker(ticker_str, session=session) if session else yf.Ticker(ticker_str)
            info = {}
            try:
                info = ticker.info or {}
            except Exception as e:
                logger.warning(f"ticker.info with session failed for {ticker_str}: {e}")

            if not info and session:
                try:
                    ticker = yf.Ticker(ticker_str)
                    info = ticker.info or {}
                except Exception:
                    pass

            # Validate real data received with multi-level price fallback
            price_raw = (info.get("currentPrice")
                         or info.get("regularMarketPrice")
                         or info.get("previousClose")
                         or info.get("regularMarketPreviousClose")
                         or info.get("navPrice"))

            if price_raw is None:
                try:
                    fast_info = ticker.fast_info
                    price_raw = fast_info.get("lastPrice") or fast_info.get("previousClose")
                except Exception:
                    pass

            if price_raw is None:
                try:
                    hist = ticker.history(period="5d")
                    if not hist.empty and 'Close' in hist.columns:
                        price_raw = float(hist['Close'].iloc[-1])
                except Exception:
                    pass

            if price_raw is None or math.isnan(price_raw):
                continue

            price        = _r(price_raw)
            hi52         = _r(info.get("fiftyTwoWeekHigh"))
            lo52         = _r(info.get("fiftyTwoWeekLow"))
            shares       = info.get("sharesOutstanding")          # absolute count
            shares_m     = _r(shares / 1_000_000) if shares else None
            market_cap   = info.get("marketCap")
            market_cap_m = _r(market_cap / 1_000_000) if market_cap else None

            # ------------------------------------------------------------------
            # Ratios available directly from info
            # ------------------------------------------------------------------
            pe           = info.get("trailingPE") or info.get("forwardPE")
            pbv          = info.get("priceToBook")
            eps          = info.get("trailingEps")
            bv_per_share = _r(price_raw / pbv) if (price_raw and pbv and pbv != 0) else None

            roe          = _pct(info.get("returnOnEquity"))   # decimal → %
            roa          = _pct(info.get("returnOnAssets"))
            npm          = _pct(info.get("profitMargins"))
            gpm          = _pct(info.get("grossMargins"))
            ebit_margin  = _pct(info.get("ebitdaMargins"))    # EBITDA margin as proxy
            de           = info.get("debtToEquity")
            de           = _r(de / 100) if de else None        # yf returns as %, convert to x

            peg          = info.get("pegRatio")
            dps          = info.get("dividendRate")             # annual THB per share
            div_yield    = _pct(info.get("dividendYield"))
            payout       = _pct(info.get("payoutRatio"))        # already %
            beta         = _r(info.get("beta"))

            revenue      = info.get("totalRevenue")
            revenue_m    = _r(revenue / 1_000_000) if revenue else None

            ebitda       = info.get("ebitda")
            ebitda_m     = _r(ebitda / 1_000_000) if ebitda else None

            total_debt   = info.get("totalDebt") or 0
            cash         = info.get("totalCash") or 0
            ev           = (market_cap + total_debt - cash
                            if (market_cap and total_debt is not None and cash is not None)
                            else None)
            ev_m         = _r(ev / 1_000_000) if ev else None
            ev_ebitda    = _r(ev / ebitda) if (ev and ebitda and ebitda != 0) else None

            # ------------------------------------------------------------------
            # DuPont components: fetch from balance sheet (info.totalAssets = None)
            # ------------------------------------------------------------------
            total_assets_abs, total_equity_abs = _get_bs_values(ticker)

            # Asset Turnover = Revenue / Total Assets
            if revenue and total_assets_abs and total_assets_abs != 0:
                asset_turnover = _r(revenue / total_assets_abs)
            else:
                asset_turnover = None

            # Financial Leverage = Total Assets / Shareholders' Equity
            if total_assets_abs and total_equity_abs and total_equity_abs != 0:
                financial_leverage = _r(total_assets_abs / total_equity_abs)
            else:
                financial_leverage = None

            total_assets_m = _r(total_assets_abs / 1_000_000) if total_assets_abs else None
            total_equity_m = _r(total_equity_abs / 1_000_000) if total_equity_abs else None

            # ROTC = Net Income / (Total Debt + Total Equity)  [approx via ROA × Total Assets / Capital]
            # ROIC = NOPAT / Invested Capital  (use ROA as proxy if missing)
            # For display, we use ROA as ROTC proxy and ROE as ROIC proxy

            # Calculate D/E from balance sheet using SET's definition: Total Liabilities / Shareholders' Equity
            # where Total Liabilities = Total Assets - Shareholders' Equity.
            # This is robust across all sectors (industrial, bank, finance) and matches official SET data.
            de_bs = None
            if total_assets_abs and total_equity_abs and total_equity_abs != 0:
                de_bs = _r((total_assets_abs - total_equity_abs) / total_equity_abs)

            if de_bs is not None:
                de = de_bs      # Always prefer the balance-sheet Total Liabilities D/E for SET stocks


            # P/S ratio
            if price and revenue and shares and shares != 0:
                ps = _r(price / (revenue / shares))
            else:
                ps = _r(info.get("priceToSalesTrailing12Months"))

            mktcap_rev = (_r(market_cap_m / revenue_m)
                          if (market_cap_m and revenue_m and revenue_m != 0) else None)

            # Company metadata
            company_name = info.get("shortName") or info.get("longName") or symbol
            company_full = info.get("longName") or company_name
            sector       = info.get("sector") or info.get("industry") or "—"
            website      = info.get("website") or ""
            industry     = info.get("industry") or "—"

            # Historical EPS (quarterly) for YoY growth
            hist_eps = _get_historical_eps(ticker)

            # ── XD Dates Extraction ───────────────────────────────────────────
            last_xd_date = None
            upcoming_xd_date = None
            try:
                from datetime import datetime
                today = datetime.now().date()
                divs = ticker.dividends
                if divs is not None and not divs.empty:
                    xd_dates = [d.date() for d in divs.index]
                    past_xd = [d for d in xd_dates if d <= today]
                    future_xd = [d for d in xd_dates if d > today]
                    if past_xd:
                        last_xd_date = max(past_xd).strftime('%d %b %Y')
                    if future_xd:
                        upcoming_xd_date = min(future_xd).strftime('%d %b %Y')
                
                # Fallback for upcoming from calendar
                if not upcoming_xd_date:
                    cal = ticker.calendar
                    if isinstance(cal, dict) and 'Ex-Dividend Date' in cal:
                        xd = cal['Ex-Dividend Date']
                        if xd and xd >= today:
                            upcoming_xd_date = xd.strftime('%d %b %Y')
            except Exception:
                pass

            def _get_f_val(df, date, keys):
                for k in keys:
                    if k in df.index:
                        val = df.loc[k, date]
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            return float(val)
                return None


            # ── Financial History Extraction ──────────────────────────────────
            financial_history = []
            try:
                # Try both financials and income_stmt as yfinance data quality varies
                f = ticker.financials
                if f is None or f.empty:
                    f = ticker.income_stmt

                # Also fetch cashflow, balance sheet, and dividends for new charts
                cf = ticker.cashflow
                bs = ticker.balance_sheet
                divs = ticker.dividends

                def _match_col_year(df, year):
                    """Find column in DataFrame matching a given year."""
                    if df is None or df.empty:
                        return None
                    for c in df.columns:
                        if c.year == year:
                            return c
                    return None

                if f is not None and not f.empty:
                    # Look back up to 10 years (yfinance may only provide 4-5 for SET stocks)
                    for col_date in f.columns[:10]:
                        try:
                            raw_rev = _get_f_val(f, col_date, ['Total Revenue', 'Revenue', 'Operating Revenue'])
                            raw_ni  = _get_f_val(f, col_date, ['Net Income', 'Net Income Common Stockholders', 'Net Income from Continuing Ops'])
                            eps_v   = _get_f_val(f, col_date, ['Basic EPS', 'Diluted EPS', 'Earnings Per Share'])
                            
                            # Fallback manual calculation if EPS is missing/NaN (e.g. yfinance data gaps)
                            if (eps_v is None or math.isnan(eps_v)) and raw_ni is not None:
                                avg_shares = _get_f_val(f, col_date, ['Basic Average Shares', 'Diluted Average Shares'])
                                if not avg_shares and shares:
                                    avg_shares = float(shares)
                                if avg_shares:
                                    eps_v = raw_ni / avg_shares

                            # Convert to Million THB for simplified axis labels
                            rev_val = (raw_rev / 1_000_000) if raw_rev is not None else None
                            ni_val  = (raw_ni / 1_000_000) if raw_ni is not None else None
                            
                            npm_val = (raw_ni / raw_rev * 100) if raw_rev and raw_ni is not None else None

                            # ── CFO: Net Cash from Operating Activities ──
                            cfo_val = None
                            cf_col = _match_col_year(cf, col_date.year)
                            if cf_col is not None:
                                raw_cfo = _get_f_val(cf, cf_col, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'])
                                if raw_cfo is not None:
                                    cfo_val = round(raw_cfo / 1_000_000, 2)

                            # ── D/E Ratio from Balance Sheet ──
                            de_val = None
                            bs_col = _match_col_year(bs, col_date.year)
                            if bs_col is not None:
                                ta = _get_f_val(bs, bs_col, ['Total Assets'])
                                se = _get_f_val(bs, bs_col, ['Stockholders Equity', 'Common Stock Equity', 'Total Equity Gross Minority Interest'])
                                if ta and se and se != 0:
                                    de_val = round((ta - se) / se, 2)

                            financial_history.append({
                                "year": str(col_date.year),
                                "revenue": rev_val,
                                "net_income": ni_val,
                                "eps": eps_v,
                                "npm": npm_val,
                                "cfo": cfo_val,
                                "de_ratio": de_val,
                                "dps": None  # filled after loop from dividends
                            })
                        except Exception:
                            continue
                    financial_history.reverse()

                # ── Fill DPS per year from dividend history ──
                if divs is not None and not divs.empty:
                    for entry in financial_history:
                        yr = int(entry["year"])
                        yr_divs = divs[divs.index.year == yr]
                        if not yr_divs.empty:
                            entry["dps"] = round(float(yr_divs.sum()), 2)

                # ── Add entry for current year in annual history (blank if no official annual data) ──
                import datetime
                current_year = datetime.datetime.now().year
                annual_years = {int(e["year"]) for e in financial_history}

                if current_year not in annual_years:
                    financial_history.append({
                        "year": str(current_year),
                        "revenue": None,
                        "net_income": None,
                        "eps": None,
                        "npm": None,
                        "cfo": None,
                        "de_ratio": None,
                        "dps": None,
                    })

            except Exception:
                pass

            # ── Quarterly Financial History ────────────────────────────────────
            quarterly_history = []
            try:
                import datetime
                q_is = ticker.quarterly_income_stmt
                q_cf = ticker.quarterly_cashflow
                q_bs = ticker.quarterly_balance_sheet
                divs_q = ticker.dividends

                # Determine fiscal year end month from annual financials
                fy_end_month = 12  # default December
                if f is not None and not f.empty and len(f.columns) > 0:
                    fy_end_month = f.columns[0].month

                # Build set of all unique quarter-end dates across all sources
                q_dates = set()
                for src in [q_is, q_cf, q_bs]:
                    if src is not None and not src.empty:
                        for c in src.columns:
                            q_dates.add(c)

                for qd in sorted(q_dates):  # chronological
                    month = qd.month
                    year = qd.year
                    # Map month to fiscal quarter based on fy_end_month
                    months_after_fy = (month - fy_end_month) % 12
                    if months_after_fy == 0:
                        q_num = 4
                    elif months_after_fy <= 3:
                        q_num = 1
                    elif months_after_fy <= 6:
                        q_num = 2
                    elif months_after_fy <= 9:
                        q_num = 3
                    else:
                        q_num = 4
                    q_lbl = f"Q{q_num}/{year}"

                    # Revenue & Net Income
                    rev_q = None; ni_q = None; eps_q = None
                    if q_is is not None and not q_is.empty and qd in q_is.columns:
                        raw_rev = _get_f_val(q_is, qd, ['Total Revenue', 'Revenue', 'Operating Revenue'])
                        raw_ni = _get_f_val(q_is, qd, ['Net Income', 'Net Income Common Stockholders'])
                        eps_q = _get_f_val(q_is, qd, ['Basic EPS', 'Diluted EPS'])
                        rev_q = round(raw_rev / 1_000_000, 2) if raw_rev is not None else None
                        ni_q = round(raw_ni / 1_000_000, 2) if raw_ni is not None else None
                        # EPS fallback
                        if (eps_q is None or (isinstance(eps_q, float) and math.isnan(eps_q))) and raw_ni is not None:
                            avg_sh = _get_f_val(q_is, qd, ['Basic Average Shares', 'Diluted Average Shares'])
                            if not avg_sh and shares:
                                avg_sh = float(shares)
                            if avg_sh:
                                eps_q = round(raw_ni / avg_sh, 2)
                        elif eps_q is not None and not (isinstance(eps_q, float) and math.isnan(eps_q)):
                            eps_q = round(eps_q, 2)
                        else:
                            eps_q = None

                    # CFO
                    cfo_q = None
                    if q_cf is not None and not q_cf.empty and qd in q_cf.columns:
                        raw_cfo = _get_f_val(q_cf, qd, ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities'])
                        if raw_cfo is not None:
                            cfo_q = round(raw_cfo / 1_000_000, 2)

                    # D/E
                    de_q = None
                    if q_bs is not None and not q_bs.empty and qd in q_bs.columns:
                        ta = _get_f_val(q_bs, qd, ['Total Assets'])
                        se = _get_f_val(q_bs, qd, ['Stockholders Equity', 'Common Stock Equity', 'Total Equity Gross Minority Interest'])
                        if ta and se and se != 0:
                            de_q = round((ta - se) / se, 2)

                    # DPS: sum dividends paid in this quarter's date range
                    dps_q = None
                    if divs_q is not None and not divs_q.empty:
                        # Ensure both index and comparison dates are tz-naive for comparison
                        q_start = qd - datetime.timedelta(days=93)
                        try:
                            qd_naive = qd.tz_localize(None) if qd.tzinfo else qd
                            q_start_naive = q_start.tz_localize(None) if q_start.tzinfo else q_start
                            div_idx_naive = divs_q.index.tz_localize(None)
                            
                            # Surgical fix: for the latest quarter, look forward 60 days to capture recently declared dividends
                            if qd == max(q_dates):
                                q_end_naive = qd_naive + datetime.timedelta(days=60)
                            else:
                                q_end_naive = qd_naive
                            
                            q_divs = divs_q[(div_idx_naive >= q_start_naive) & (div_idx_naive <= q_end_naive)]
                            if not q_divs.empty:
                                dps_q = round(float(q_divs.sum()), 2)
                        except Exception:
                            pass

                    # Only include if we have at least one data point
                    if any(v is not None for v in [rev_q, ni_q, eps_q, cfo_q, de_q, dps_q]):
                        quarterly_history.append({
                            "quarter": q_lbl,
                            "revenue": rev_q,
                            "net_income": ni_q,
                            "eps": eps_q,
                            "cfo": cfo_q,
                            "de_ratio": de_q,
                            "dps": dps_q,
                        })
            except Exception:
                pass

            # ── Keep only the latest 5 quarters of active data ──────────────────
            try:
                if len(quarterly_history) > 5:
                    quarterly_history = quarterly_history[-5:]
            except Exception:
                pass

            # ── Patch Prev Year Annual EPS if missing from quarterly ──────────
            if hist_eps and hist_eps.get("prev_year_annual_eps") is None:
                if financial_history:
                    try:
                        # If Q4 (multiplier == 1.0), the current year is the last element,
                        # so the previous year is the second to last (-2).
                        # If Q1-Q3, the current year isn't fully reported yet,
                        # so the previous year is the last element (-1).
                        idx = -2 if hist_eps.get("multiplier") == 1.0 else -1
                        prev_year_eps = financial_history[idx].get("eps")
                        if prev_year_eps is not None:
                            hist_eps["prev_year_annual_eps"] = float(prev_year_eps)
                    except IndexError:
                        pass

            return {
                "ticker":            ticker_str,
                "company_name":      company_name,
                "company_full":      company_full,
                "sector":            sector,
                "industry":          industry,
                "website":           website,
                "last_xd_date":      last_xd_date,
                "upcoming_xd_date":  upcoming_xd_date,
                "financial_history": financial_history,
                "quarterly_history": quarterly_history,
                "price":             price,
                "hi_52wk":           hi52,
                "lo_52wk":           lo52,
                "shares_m":          shares_m,
                "market_cap_m":      market_cap_m,
                "pe":                _r(pe),
                "pbv":               _r(pbv),
                "eps":               _r(eps),
                "bv_per_share":      bv_per_share,
                "roe":               roe,          # already in %
                "roa":               roa,          # already in %
                "npm":               npm,          # already in %
                "gpm":               gpm,          # already in %
                "ebit_margin":       ebit_margin,  # already in %
                "de":                de,
                "peg":               _r(peg),
                "dps":               _r(dps),
                "dividend_yield":    div_yield,
                "payout":            payout,       # already in %
                "revenue_m":         revenue_m,
                "ebitda_m":          ebitda_m,
                "ev_m":              ev_m,
                "ev_ebitda":         ev_ebitda,
                "beta":              beta,
                # DuPont (fixed)
                "financial_leverage": financial_leverage,
                "asset_turnover":     asset_turnover,
                "total_assets_m":     total_assets_m,
                "total_equity_m":     total_equity_m,
                # Other
                "ps":                ps,
                "mktcap_rev":        mktcap_rev,
                "total_debt_m":      _r(total_debt / 1_000_000) if total_debt else None,
                "cash_m":            _r(cash / 1_000_000) if cash else None,
                "net_debt_m":        _r((total_debt - cash) / 1_000_000),
                "hist_eps":          hist_eps,
                "error":             None,
            }

        except Exception as e:
            logger.warning(f"yfinance failed for {ticker_str}: {e}")
            continue

    return {"error": f"No data found for symbol '{symbol}'. Check the SET ticker."}


# ---------------------------------------------------------------------------
# Balance Sheet helpers
# ---------------------------------------------------------------------------
def _get_bs_values(ticker) -> tuple:
    """
    Fetch Total Assets and Total Equity (Common Stock Equity / Stockholders Equity)
    from the annual balance sheet.  Returns (total_assets, total_equity) as floats
    or (None, None) if unavailable.
    """
    try:
        bs = ticker.balance_sheet
        if bs is None or bs.empty:
            return None, None

        col = bs.columns[0]   # Most recent year

        def _bs_row(*names):
            for name in names:
                if name in bs.index:
                    v = bs.loc[name, col]
                    if not _is_nan(v):
                        return float(v)
            return None

        total_assets = _bs_row("Total Assets")
        total_equity = _bs_row(
            "Common Stock Equity",
            "Stockholders Equity",
            "Total Equity Gross Minority Interest",
            "Tangible Book Value",
        )
        return total_assets, total_equity

    except Exception as e:
        logger.debug(f"Balance sheet fetch failed: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Historical EPS
# ---------------------------------------------------------------------------
def _get_historical_eps(ticker) -> dict:
    """
    Try quarterly income statement for YoY EPS growth calculation.
    Skips NaN quarters to find the most recent valid data.
    Detects fiscal quarter (Q1-Q4) and sets multiplier for forecasting.
    Returns dict with curr_q_eps, prev_q_eps, annual_eps, q_label, multiplier.
    """
    try:
        import pandas as pd
        q_income = ticker.quarterly_income_stmt
        if q_income is None or q_income.empty:
            return {}

        # Ensure columns are sorted by date descending (latest first)
        q_income = q_income.reindex(sorted(q_income.columns, reverse=True), axis=1)

        # 1. Identify primary EPS rows
        eps_rows = [r for r in q_income.index
                    if "diluted eps" in str(r).lower()
                    or "basic eps" in str(r).lower()
                    or ("eps" in str(r).lower() and "excl" not in str(r).lower())]
        
        # 2. Identify Net Income and Share rows for manual fallbacks
        ni_rows = [r for r in q_income.index if "net income common stockholders" in str(r).lower()]
        if not ni_rows:
            ni_rows = [r for r in q_income.index if "net income" in str(r).lower()]
            
        share_rows = [r for r in q_income.index if "diluted average shares" in str(r).lower()]
        if not share_rows:
            share_rows = [r for r in q_income.index if "basic average shares" in str(r).lower()]

        # Fallback share count from ticker info
        info_shares = ticker.info.get('sharesOutstanding')

        valid_eps = []
        valid_dates = []
        
        for date in q_income.columns:
            eps_val = None
            
            # A. Try direct EPS row
            if eps_rows:
                eps_val = _safe_float(q_income.loc[eps_rows[0], date])
            
            # B. If direct EPS is missing, try manual calculation (Net Income / Shares)
            if eps_val is None and ni_rows:
                ni = _safe_float(q_income.loc[ni_rows[0], date])
                if ni is not None:
                    # Try quarterly shares first
                    sh = None
                    if share_rows:
                        sh = _safe_float(q_income.loc[share_rows[0], date])
                    
                    # If quarterly shares missing, use global shares from info
                    if sh is None:
                        sh = info_shares
                        
                    if sh and sh > 0:
                        eps_val = ni / sh
            
            if eps_val is not None:
                valid_eps.append(eps_val)
                valid_dates.append(date)

        if not valid_eps:
            return {}

        # TTM EPS (sum of last 4 quarters)
        ttm_eps = sum(valid_eps[:4]) if len(valid_eps) >= 4 else sum(valid_eps)

        # 3. Detect Fiscal Year End Month (default 12)
        fy_end_month = 12
        try:
            # Check annual financials for the fiscal year end month
            ann = ticker.financials
            if ann is not None and not ann.empty:
                fy_end_month = ann.columns[0].month
        except:
            pass

        # 4. Detect Quarter and Multiplier based on Fiscal Year End
        d = valid_dates[0]
        month, year = d.month, d.year
        
        # Calculate how many months have passed since fiscal year end
        months_after_fy = (month - fy_end_month + 12) % 12
        if months_after_fy == 0:
            q_num = 4; multiplier = 1.0; q_year = year
        else:
            if months_after_fy <= 3: q_num = 1; multiplier = 4.0
            elif months_after_fy <= 6: q_num = 2; multiplier = 2.0
            elif months_after_fy <= 9: q_num = 3; multiplier = 1.33
            else: q_num = 4; multiplier = 1.0
            
            # If month > fy_end_month, it belongs to the NEXT fiscal year
            q_year = year if month <= fy_end_month else year + 1

        q_label = f"Q{q_num} {q_year}"
        logger.info(f"Detected {q_label} (month {month}, fy_end {fy_end_month}) -> Multiplier {multiplier}")

        # Calculate Previous Year's Annual EPS (sum of the 4 quarters exactly 1 year ago)
        # For Q4 (q_num=4), we want sum(valid_eps[4:8])
        # For Q1 (q_num=1), we want sum(valid_eps[1:5])
        if len(valid_eps) >= q_num + 3:
            prev_year_annual = sum(valid_eps[q_num : q_num + 4])
        else:
            # Fallback to annual financials if quarterly history is too short
            prev_year_annual = None
            try:
                ann = ticker.financials
                if ann is not None and not ann.empty:
                    # Index 1 is usually the previous year
                    # But if we are in Q4 (multiplier=1), index 1 is the previous year
                    # If we are in Q1-Q3, index 0 is the previous year (because the current isn't in annuals yet)
                    idx = 1 if multiplier == 1.0 else 0
                    if len(ann.columns) > idx:
                        a_eps_rows = [r for r in ann.index if "eps" in str(r).lower() and "excl" not in str(r).lower()]
                        if a_eps_rows:
                            prev_year_annual = _safe_float(ann.loc[a_eps_rows[0], ann.columns[idx]])
            except:
                pass

        return {
            "curr_q_eps": valid_eps[0], 
            "ttm_eps": ttm_eps, 
            "prev_year_annual_eps": prev_year_annual,
            "q_label":    q_label,
            "multiplier": multiplier
        }

    except Exception as e:
        logger.debug(f"Quarterly EPS extraction failed: {e}")
    return {}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _pct(v) -> float:
    """yfinance decimal proportion → percentage (e.g. 0.15 → 15.00)."""
    if v is None:
        return None
    try:
        return round(float(v) * 100, 2)
    except (TypeError, ValueError):
        return None


def _r(v, decimals: int = 2):
    """Safe round."""
    if v is None:
        return None
    try:
        return round(float(v), decimals)
    except (TypeError, ValueError):
        return None


def _safe_float(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except Exception:
        return None


def _is_nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Sector classification
# ---------------------------------------------------------------------------
def determine_sector_type(sector: str, industry: str = "") -> str:
    """
    Returns 'banking', 'finance', or 'others'.
    Checks both sector and industry strings from yfinance.
    """
    combined = (sector + " " + industry).lower()
    if "bank" in combined:
        return "banking"
    if any(k in combined for k in ["financ", "securities", "leas", "credit", "insurance"]):
        return "finance"
    return "others"


# ---------------------------------------------------------------------------
# Thai 10-Year Bond Yield  (Selenium → yfinance → fallback)
# ---------------------------------------------------------------------------
_cached_bond_yield = None
_cached_bond_source = None   # tracks where the yield came from


def get_bond_yield() -> float:
    """
    Fetch Thailand 10-year government bond yield from ThaiBMA.
    Strategy: Selenium scrape → yfinance fallback → hardcoded fallback.
    Caches result for the entire server session.
    Returns decimal (e.g. 0.0238 for 2.38%).
    """
    global _cached_bond_yield, _cached_bond_source
    if _cached_bond_yield is not None:
        return _cached_bond_yield

    # ── Method 1: MarketWatch via Requests ───────────────────────────────
    yield_val = _scrape_marketwatch_yield()
    if yield_val is not None:
        _cached_bond_yield = yield_val
        _cached_bond_source = "MarketWatch (Live)"
        logger.info(f"Thai 10Y yield (MarketWatch): {yield_val*100:.4f}%")
        return yield_val

    # ── Method 2: yfinance fallback ──────────────────────────────────
    try:
        import yfinance as yf
        session = get_yf_session()
        t = yf.Ticker("TH10Y=RR", session=session) if session else yf.Ticker("TH10Y=RR")
        info = t.info
        y = info.get("regularMarketPrice") or info.get("previousClose")
        if y and float(y) > 0:
            yield_val = round(float(y) / 100, 6)
            _cached_bond_yield = yield_val
            _cached_bond_source = "yfinance"
            logger.info(f"ThaiBMA 10Y yield (yfinance): {yield_val*100:.4f}%")
            return yield_val
    except Exception:
        pass

    # ── Method 3: Hardcoded fallback (last known value) ──────────────
    _cached_bond_yield = 0.0238   # 2.38%
    _cached_bond_source = "Fallback (Offline)"
    logger.info("ThaiBMA 10Y yield: using fallback 2.38%")
    return _cached_bond_yield


def get_bond_yield_source() -> str:
    """Return a human-readable string describing where the bond yield came from."""
    return _cached_bond_source or "Unknown"


def _scrape_marketwatch_yield() -> float:
    """
    Scrape Thailand 10-year government bond yield from MarketWatch.
    Uses standard requests with browser headers. Works on Cloud/Render environments.
    """
    import requests
    from bs4 import BeautifulSoup

    url = 'https://www.marketwatch.com/investing/bond/ambmkth-10y?countrycode=bx&eafs_enabled=false'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            price_tag = soup.find('h2', {'class': 'intraday__price'})
            if price_tag:
                span = price_tag.find('bg-quote', {'class': 'value'}) or price_tag.find('span', {'class': 'value'})
                if span:
                    yield_pct = float(span.text)
                    return round(yield_pct / 100, 6)
    except Exception as e:
        logger.warning(f"MarketWatch scrape failed: {e}")
        
    return None


# ---------------------------------------------------------------------------
# Momentum / Volume Data
# ---------------------------------------------------------------------------
def get_momentum_data(symbol: str) -> dict:
    """
    Fetch 1-month historical OHLCV data from yfinance for momentum analysis.
    Returns volume metrics, price gaps, and momentum signals.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"error": "yfinance/pandas not installed"}

    symbol_clean = symbol.upper().removesuffix(".BK")
    ticker_str = f"{symbol_clean}.BK"

    try:
        session = get_yf_session()
        ticker = yf.Ticker(ticker_str, session=session) if session else yf.Ticker(ticker_str)
        hist = ticker.history(period="1mo")

        if hist is None or hist.empty or len(hist) < 2:
            return {"error": f"No historical data for {symbol_clean}"}

        # Build daily records
        daily = []
        for i, (date, row) in enumerate(hist.iterrows()):
            prev_close = hist.iloc[i - 1]["Close"] if i > 0 else row["Open"]
            change_pct = ((row["Close"] - prev_close) / prev_close * 100) if prev_close else 0
            daily.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "change_pct": round(change_pct, 2),
            })

        if len(daily) < 2:
            return {"error": "Insufficient data"}

        today = daily[-1]
        yesterday = daily[-2]

        # Volume averages
        volumes = [d["volume"] for d in daily]
        avg_5d = sum(volumes[-5:]) / min(len(volumes), 5) if volumes else 1
        avg_20d = sum(volumes) / len(volumes) if volumes else 1

        vol_ratio_5d = round(today["volume"] / avg_5d, 2) if avg_5d > 0 else 0
        vol_ratio_20d = round(today["volume"] / avg_20d, 2) if avg_20d > 0 else 0

        # Price gap (open today vs close yesterday)
        price_gap = round(today["open"] - yesterday["close"], 2)
        price_gap_pct = round(price_gap / yesterday["close"] * 100, 2) if yesterday["close"] else 0

        # Price change (close today vs close yesterday)
        price_change = round(today["close"] - yesterday["close"], 2)
        price_change_pct = round(price_change / yesterday["close"] * 100, 2) if yesterday["close"] else 0

        # Volume spike detection
        volume_spike = vol_ratio_5d > 1.5

        # Gap detection
        gap_up = price_gap_pct > 0.3     # >0.3% gap up
        gap_down = price_gap_pct < -0.3  # >0.3% gap down

        # Institute vs Retail estimation (heuristic)
        if vol_ratio_20d > 2.0:
            est_inst = 45
        elif vol_ratio_20d > 1.5:
            est_inst = 38
        elif vol_ratio_20d > 1.0:
            est_inst = 30
        else:
            est_inst = 22
        est_retail = 100 - est_inst

        # Momentum signal
        if volume_spike and gap_up and price_change_pct > 0:
            signal = "STRONG BUY"
        elif volume_spike and price_change_pct > 0:
            signal = "BUY"
        elif volume_spike and gap_down and price_change_pct < 0:
            signal = "STRONG SELL"
        elif volume_spike and price_change_pct < 0:
            signal = "SELL"
        elif price_change_pct > 0:
            signal = "BULLISH"
        elif price_change_pct < 0:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        # Consecutive up/down days
        consec_up = 0
        consec_down = 0
        for d in reversed(daily):
            if d["change_pct"] > 0:
                consec_up += 1
            else:
                break
        for d in reversed(daily):
            if d["change_pct"] < 0:
                consec_down += 1
            else:
                break

        return {
            "daily": daily,
            "today_date": today["date"],
            "yesterday_date": yesterday["date"],
            "today_volume": today["volume"],
            "avg_5d_volume": round(avg_5d),
            "avg_20d_volume": round(avg_20d),
            "volume_ratio_5d": vol_ratio_5d,
            "volume_ratio_20d": vol_ratio_20d,
            "price_gap": price_gap,
            "price_gap_pct": price_gap_pct,
            "price_change": price_change,
            "price_change_pct": price_change_pct,
            "today_close": today["close"],
            "today_open": today["open"],
            "yesterday_close": yesterday["close"],
            "est_institute_pct": est_inst,
            "est_retail_pct": est_retail,
            "volume_spike": volume_spike,
            "gap_up": gap_up,
            "gap_down": gap_down,
            "momentum_signal": signal,
            "consec_up": consec_up,
            "consec_down": consec_down,
            "error": None,
        }

    except Exception as e:
        logger.warning(f"Momentum data failed for {symbol}: {e}")
        return {"error": str(e)}


def get_historical_ohlcv(symbol: str, period: str = "1y") -> dict:
    """
    Fetch historical OHLCV data for technical charting.
    Calculates EMA50 and EMA200.
    Returns data formatted for Lightweight Charts.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {"error": "yfinance/pandas not installed"}

    symbol_clean = symbol.upper().removesuffix(".BK")
    ticker_str = f"{symbol_clean}.BK"

    try:
        session = get_yf_session()
        ticker = yf.Ticker(ticker_str, session=session) if session else yf.Ticker(ticker_str)
        # Fetch slightly more data to ensure EMAs are calculated correctly at the start of the requested period
        hist = ticker.history(period=period)

        if hist is None or hist.empty:
            return {"error": f"No historical data found for {symbol_clean}"}

        # Calculate EMAs
        hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()
        hist['EMA200'] = hist['Close'].ewm(span=200, adjust=False).mean()

        chart_data = []
        for date, row in hist.iterrows():
            # Check for NaN in EMAs (only occurs if not enough data)
            ema50 = float(row["EMA50"])
            ema200 = float(row["EMA200"])
            
            chart_data.append({
                "time":  date.strftime("%Y-%m-%d"),
                "open":  round(float(row["Open"]), 2),
                "high":  round(float(row["High"]), 2),
                "low":   round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "ema50":  round(ema50, 2) if not pd.isna(ema50) else None,
                "ema200": round(ema200, 2) if not pd.isna(ema200) else None,
            })

        return {
            "symbol": symbol_clean,
            "data": chart_data,
            "error": None
        }

    except Exception as e:
        logger.warning(f"Historical OHLCV failed for {symbol}: {e}")
        return {"error": str(e)}
