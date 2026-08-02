"""
ai_ranking_engine.py
--------------------
AI Stock Selection & Ranking Engine for SET-listed stocks.
Processes stocks through 5 multi-dimensional stages:
  1. Technical Screening (EMA, RSI, Stochastic, MACD, PSAR, BB)
  2. Fundamental & Intrinsic Valuation (DCF, DDM, PER, PBV, Bank Gordon Growth)
  3. News Sentiment & Catalyst Aggregation (SET, Yahoo, Thunhoon, GapFocus, RYT9)
  4. Momentum & Volume Spike Detection (RVOL, 5-day avg volume, price gaps)
  5. Multi-Factor Weighted Scoring & AI Synthesis (Top 10 Ranked Output)
"""

import os
import json
import logging
import time
import requests
from datetime import datetime
import numpy as np

from screening_engine import run_screening, get_default_date
from data_fetcher import get_yf_data, get_momentum_data, determine_sector_type
from valuation_engine import (
    calc_fair_value_dcf,
    calc_fair_value_per,
    calc_fair_value_pbv,
    build_bank_valuation,
    calc_margin_of_safety,
    safe_float
)
from set50_list import is_set50, is_set100
from news_fetcher import get_all_news

logger = logging.getLogger(__name__)

# System default scoring weights (40% Tech / 40% Fund / 15% Mom / 5% News)
DEFAULT_WEIGHTS = {
    "weight_tech": 0.40,
    "weight_fund": 0.40,
    "weight_mom": 0.15,
    "weight_news": 0.05
}

CANDIDATE_CAP = 25  # Default candidate cap if process_all=False

# (Lines 46 to 326 remain unchanged)



def compute_stock_valuation(yf_raw):
    """
    Computes fair value and valuation metrics for a stock matching app.py logic.
    Returns dict with fair_value and fair_value_method_note for UI explanation.
    """
    price = safe_float(yf_raw.get("price"))
    eps = safe_float(yf_raw.get("eps"))
    pe = safe_float(yf_raw.get("pe"))
    pbv = safe_float(yf_raw.get("pbv"))
    bv_ps = safe_float(yf_raw.get("bv_per_share"))
    dps = safe_float(yf_raw.get("dps"))
    roe = safe_float(yf_raw.get("roe"))
    payout_pct = safe_float(yf_raw.get("payout")) or 50.0

    info_dict = yf_raw.get("info") or {}
    sector_raw = yf_raw.get("sector") or info_dict.get("sector") or ""
    industry_raw = yf_raw.get("industry") or info_dict.get("industry") or ""
    sector_type = determine_sector_type(sector_raw, industry_raw)
    is_financial = sector_type in ("banking", "finance")

    # Additional metrics for Buffett & Peter Lynch model
    peg = safe_float(info_dict.get("pegRatio") or yf_raw.get("peg_ratio"))
    de_ratio = safe_float(info_dict.get("debtToEquity") or yf_raw.get("debt_to_equity"))
    div_yield = safe_float(info_dict.get("dividendYield") or yf_raw.get("div_yield"))
    net_margin = safe_float(info_dict.get("profitMargins") or yf_raw.get("net_margin"))
    fcf = safe_float(info_dict.get("freeCashflow") or yf_raw.get("fcf"))

    fair_val = 0.0
    method_note = "N/A"

    if is_financial:
        rf = 0.022
        beta = safe_float(yf_raw.get("beta"), 1.0)
        cost_of_equity = rf + beta * 0.06
        bank_vals = build_bank_valuation(
            price=price,
            bv_per_share=bv_ps,
            roe_pct=roe,
            eps=eps,
            dps=dps,
            payout_pct=payout_pct,
            cost_of_equity=cost_of_equity,
            pe_benchmark=15.0,
            pbv_benchmark=1.5,
            g_terminal=0.03
        )
        fair_val = safe_float(bank_vals.get("fv_div") or bank_vals.get("fv_ddm") or bank_vals.get("fv_pbv") or 0.0)
        method_note = "Bank Justified P/BV & DDM Model"
    else:
        revenue_m = safe_float(yf_raw.get("revenue_m"))
        ebit_margin_dec = (safe_float(yf_raw.get("ebit_margin")) or 10.0) / 100.0
        shares_m = safe_float(yf_raw.get("shares_m"))
        net_debt_m = safe_float(yf_raw.get("net_debt_m"))

        rf = 0.022
        beta = safe_float(yf_raw.get("beta"), 1.0)
        wacc = rf + beta * 0.06

        fv_dcf = calc_fair_value_dcf(
            revenue=revenue_m,
            ebit_margin=ebit_margin_dec,
            tax_rate=0.20,
            da_ratio=0.05,
            capex_ratio=0.06,
            nwc_ratio=0.02,
            sale_growth_y1_5=0.05,
            sale_growth_y6_10=0.02,
            wacc=wacc,
            g_terminal=0.03,
            shares_m=shares_m,
            net_debt=net_debt_m
        )
        fv_per = calc_fair_value_per(eps, 15.0)
        fv_pbv = calc_fair_value_pbv(bv_ps, 1.5)

        if fv_dcf and fv_dcf > 0:
            fair_val = fv_dcf
            method_note = "10-Yr CAPM DCF Model"
        else:
            valid_vals = [v for v in [fv_per, fv_pbv] if v and v > 0]
            fair_val = float(np.mean(valid_vals)) if valid_vals else 0.0
            method_note = "Relative PER & PBV Avg (DCF N/A)"

    return {
        "price": price,
        "fair_value": round(fair_val, 2),
        "roe": roe,
        "pe": pe,
        "pbv": pbv,
        "peg": peg,
        "debt_to_equity": de_ratio,
        "div_yield": div_yield,
        "net_margin": net_margin,
        "fcf": fcf,
        "fair_value_method_note": method_note
    }


def compute_technical_score(stock_row):
    """
    Score 0-100 based on technical indicator setup from screening result.
    Gives explicit bonus for passing more criteria (6 criteria > 5 criteria > 4 criteria).
    """
    score = 40.0
    try:
        criteria_passed = int(stock_row.get('criteria_passed', 4))
        if criteria_passed == 6:
            score += 30.0
        elif criteria_passed == 5:
            score += 20.0
        elif criteria_passed >= 4:
            score += 10.0

        rsi = safe_float(stock_row.get('rsi', stock_row.get('RSI', 50)))
        stoch = safe_float(stock_row.get('stoch', stock_row.get('STOCHk', 50)))
        
        # RSI component (Oversold ~30 is ideal)
        if rsi <= 35:
            score += 15.0
        elif rsi <= 45:
            score += 10.0
        elif rsi >= 70:
            score -= 10.0

        # Stochastic component
        if stoch <= 30:
            score += 10.0
        elif stoch >= 80:
            score -= 5.0

        # Trend alignment (EMA200 / Price)
        price = safe_float(stock_row.get('close', stock_row.get('Price', 0)))
        ema200 = safe_float(stock_row.get('ema200', stock_row.get('EMA200', 0)))
        if price > 0 and ema200 > 0:
            if price >= ema200:
                score += 5.0
    except Exception as e:
        logger.warning(f"Error computing tech score: {e}")
        
    return float(np.clip(score, 0, 100))


def compute_fundamental_score(fund_data):
    """
    Score 0-100 based on Warren Buffett & Peter Lynch Fundamental Principles (v5.0):
    1. Margin of Safety & Valuation (Buffett) - Max 30 pts
    2. Capital Efficiency & Moat - ROE & Net Margin (Buffett) - Max 25 pts
    3. GARP Valuation - PEG Ratio (Peter Lynch) - Max 20 pts
    4. Balance Sheet Health & Leverage - Debt to Equity (Buffett & Lynch) - Max 15 pts
    5. Shareholder Yield & Free Cash Flow (Buffett & Lynch) - Max 10 pts
    """
    score = 0.0
    try:
        pe = safe_float(fund_data.get('pe', 0))
        pbv = safe_float(fund_data.get('pbv', 0))
        roe = safe_float(fund_data.get('roe', 0))
        if 0 < roe < 1.0:
            roe = roe * 100.0
        mos = safe_float(fund_data.get('mos', 0))
        peg = safe_float(fund_data.get('peg', 0))
        de_ratio = safe_float(fund_data.get('debt_to_equity', 0))
        if de_ratio > 10.0:
            de_ratio = de_ratio / 100.0
        div_yield = safe_float(fund_data.get('div_yield', 0))
        if 0 < div_yield < 1.0:
            div_yield = div_yield * 100.0
        net_margin = safe_float(fund_data.get('net_margin', 0))
        if 0 < net_margin < 1.0:
            net_margin = net_margin * 100.0
        fcf = safe_float(fund_data.get('fcf', 0))

        # Pillar 1: Margin of Safety & Intrinsic Valuation (Max 30 pts) - Buffett
        if mos >= 30.0:
            score += 30.0
        elif mos >= 15.0:
            score += 20.0
        elif mos >= 0.0:
            score += 10.0
        elif mos < -20.0:
            score -= 15.0

        # Pillar 2: Capital Efficiency & Economic Moat - ROE & Net Margin (Max 25 pts) - Buffett
        if roe >= 20.0 and net_margin >= 12.0:
            score += 25.0
        elif roe >= 15.0:
            score += 18.0
        elif roe >= 10.0:
            score += 10.0
        elif roe >= 0.0:
            score += 5.0
        else:
            score -= 15.0

        # Pillar 3: GARP Valuation - PEG Ratio (Max 20 pts) - Peter Lynch
        if 0 < peg <= 0.5:
            score += 20.0
        elif 0.5 < peg <= 0.8:
            score += 15.0
        elif 0.8 < peg <= 1.2:
            score += 8.0
        elif peg > 2.0:
            score -= 10.0
        elif peg == 0 and 0 < pe <= 15:
            score += 12.0

        # Pillar 4: Balance Sheet Health & Leverage (Max 15 pts) - Buffett & Lynch
        if 0 < de_ratio < 0.5:
            score += 15.0
        elif 0.5 <= de_ratio <= 1.0:
            score += 10.0
        elif 1.0 < de_ratio <= 2.0:
            score += 5.0
        elif de_ratio > 2.0:
            score -= 10.0
        elif de_ratio == 0:
            score += 10.0

        # Pillar 5: Shareholder Yield & Cash Flow (Max 10 pts) - Buffett & Lynch
        if div_yield >= 4.0 and fcf >= 0:
            score += 10.0
        elif div_yield >= 2.0:
            score += 6.0
        elif div_yield > 0:
            score += 3.0

    except Exception as e:
        logger.warning(f"Error computing fundamental score: {e}")

    return float(np.clip(score, 0, 100))


def compute_momentum_score(mom_data):
    """
    Score 0-100 based on volume spike, RVOL, and price action.
    """
    score = 50.0
    try:
        vol_spike = mom_data.get('vol_spike', False)
        rvol = safe_float(mom_data.get('rvol', 1.0))
        change_pct = safe_float(mom_data.get('change_pct', 0))

        if vol_spike:
            score += 25.0
        if rvol >= 1.5:
            score += 15.0
        elif rvol >= 1.2:
            score += 10.0

        if change_pct > 0:
            score += 10.0
        elif change_pct < -3.0:
            score -= 10.0

    except Exception as e:
        logger.warning(f"Error computing momentum score: {e}")

    return float(np.clip(score, 0, 100))


def compute_news_score(news_items):
    """
    Score 0-100 based on headline sentiment analysis.
    """
    if not news_items:
        return 50.0

    pos_keywords = ['growth', 'profit', 'dividend', 'record', 'gain', 'surge', 'expand', 'up', 'กำไร', 'เติบโต', 'ปันผล']
    neg_keywords = ['loss', 'drop', 'fall', 'decline', 'risk', 'lawsuit', 'debt', 'down', 'ขาดทุน', 'ลดลง', 'เสี่ยง']

    score = 50.0
    for item in news_items:
        title = item.get('title', '').lower()
        pos_count = sum(1 for kw in pos_keywords if kw in title)
        neg_count = sum(1 for kw in neg_keywords if kw in title)

        score += (pos_count * 5.0) - (neg_count * 5.0)

    return float(np.clip(score, 10, 95))


def query_gemini_ai(payload, api_key):
    """
    Queries Google Gemini API to produce executive investment thesis and AI score refinement for top candidate stocks.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    prompt = f"""
You are an expert Chief Financial Officer and Quantitative Portfolio Manager analyzing SET-listed stocks.
You are given a JSON dataset of candidate stocks that passed technical screening, fundamentals, news, and momentum checks.

Candidate Stock Data:
{json.dumps(payload, indent=2, ensure_ascii=False)}

Your Task:
1. Review the technical score, fundamental metrics (Fair Value, MOS %, ROE, P/E), momentum, and news sentiment for each stock.
2. Select and rank the TOP 10 stocks.
3. For each top 10 stock, generate:
   - "investment_thesis": Concise 2-sentence rationale on why this stock is a top pick.
   - "key_risks": Primary risk factor to watch out for.
   - "ai_grade": Grade string ("A+", "A", "A-", "B+", "B").
   - "ai_summary": 1-sentence summary of technical vs fundamental setup.

Return ONLY a valid JSON object matching this schema:
{{
  "top_10": [
    {{
      "rank": 1,
      "symbol": "TICKER",
      "ai_score": 92.5,
      "ai_grade": "A+",
      "investment_thesis": "...",
      "key_risks": "...",
      "ai_summary": "..."
    }}
  ]
}}
Do not include markdown code block backticks. Return raw JSON string only.
"""

    req_body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
    }

    try:
        resp = requests.post(url, headers=headers, json=req_body, timeout=25)
        if resp.status_code == 200:
            res_json = resp.json()
            raw_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.replace("```", "").strip()
            parsed = json.loads(raw_text)
            return parsed.get("top_10", [])
        else:
            logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Gemini API query error: {e}")

    return None


def run_ai_stock_selection(weights=None, date_str=None, rsi=30, stoch=70, min_criteria=4, set50_only=False, index_filter="all", process_all=True, progress_callback=None):
    """
    Runs the complete 5-stage AI Stock Selection Engine.
    Supports index_filter ("all", "set50", "set100"), criteria count priority, and fair_value_method_note.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    w_tech = safe_float(weights.get("weight_tech", 0.40))
    w_fund = safe_float(weights.get("weight_fund", 0.40))
    w_mom  = safe_float(weights.get("weight_mom", 0.15))
    w_news = safe_float(weights.get("weight_news", 0.05))

    # Support backwards compatibility for set50_only
    if set50_only and index_filter == "all":
        index_filter = "set50"

    # Normalize weights so sum = 1.0
    total_w = w_tech + w_fund + w_mom + w_news
    if total_w > 0:
        w_tech /= total_w
        w_fund /= total_w
        w_mom /= total_w
        w_news /= total_w

    if date_str is None:
        date_str = str(get_default_date())

    def notify(stage, current, total, msg=""):
        if progress_callback:
            progress_callback({
                'stage': stage,
                'current': current,
                'total': total,
                'message': msg
            })

    # STAGE 1: Technical Screening (Minimum 4 Criteria Filter & Priority Sorting)
    notify(1, 0, 100, f"Stage 1/5: Running Technical Screening (Min {min_criteria} Criteria, Index={index_filter.upper()})...")
    screen_results = run_screening(date_str, rsi, stoch)
    results_dict = screen_results.get('results', {})
    
    matched_stocks = []
    # Collect candidate stocks passing min_criteria (6 criteria -> 5 criteria -> 4 criteria)
    min_c = max(1, min(6, int(min_criteria)))
    valid_c_counts = [str(i) for i in range(6, min_c - 1, -1)]
    for c_count in valid_c_counts:
        stocks_list = results_dict.get(c_count, [])
        for s_item in stocks_list:
            s_item['criteria_passed'] = int(c_count)
            matched_stocks.append(s_item)

    # Filter for index if index_filter option is enabled
    if index_filter == "set50":
        matched_stocks = [s for s in matched_stocks if is_set50(s.get('symbol') or s.get('Symbol', ''))]
    elif index_filter == "set100":
        matched_stocks = [s for s in matched_stocks if is_set100(s.get('symbol') or s.get('Symbol', ''))]

    if not matched_stocks:
        idx_msg = f" in {index_filter.upper()} Index" if index_filter != "all" else ""
        return {
            "status": "error",
            "message": f"No stocks matched technical screening criteria (Minimum {min_c} criteria required{idx_msg}).",
            "rankings": [],
            "generated_at": datetime.now().isoformat()
        }

    # Priority sort: 6 criteria -> 5 criteria -> 4 criteria
    matched_stocks.sort(key=lambda x: x.get('criteria_passed', 4), reverse=True)

    # Candidate pool selection
    if process_all:
        candidates = matched_stocks
    else:
        candidates = matched_stocks[:CANDIDATE_CAP]

    total_candidates = len(candidates)
    notify(1, 100, 100, f"Stage 1 Complete: Found {len(matched_stocks)} stocks meeting {min_c}+ criteria. Analyzing {total_candidates} candidates.")

    candidate_dataset = []

    # STAGE 2-4: Fundamentals, News & Momentum Data Gathering
    for idx, row in enumerate(candidates, 1):
        sym = row.get('symbol') or row.get('Symbol')
        notify(2, idx, total_candidates, f"Stage 2-4/5: Analyzing Fundamentals & News for {sym} ({idx}/{total_candidates})...")

        # Technical Score (includes criteria bonus: 6 -> +30, 5 -> +20, 4 -> +10)
        tech_score = compute_technical_score(row)

        # Fundamentals & Intrinsic Valuation
        yf_raw = get_yf_data(sym)
        val_res = compute_stock_valuation(yf_raw)

        price = val_res['price']
        if price == 0:
            price = safe_float(row.get('close', row.get('Price', 0)))

        fair_val = val_res['fair_value']
        fv_method_note = val_res.get('fair_value_method_note', 'N/A')
        mos_pct = calc_margin_of_safety(fair_val, price) if (fair_val > 0 and price > 0) else 0.0

        pe_val = val_res['pe'] if val_res['pe'] > 0 else safe_float(row.get('pe', row.get('P/E', 0)))
        pbv_val = val_res['pbv'] if val_res['pbv'] > 0 else safe_float(row.get('pbv', row.get('P/BV', 0)))

        fund_info = {
            'pe': pe_val,
            'pbv': pbv_val,
            'roe': val_res['roe'],
            'mos': mos_pct,
            'peg': val_res.get('peg', 0),
            'debt_to_equity': val_res.get('debt_to_equity', 0),
            'div_yield': val_res.get('div_yield', 0),
            'net_margin': val_res.get('net_margin', 0),
            'fcf': val_res.get('fcf', 0)
        }
        fund_score = compute_fundamental_score(fund_info)

        # Momentum
        mom_data = get_momentum_data(sym)
        mom_score = compute_momentum_score(mom_data)

        # News & Sentiment
        news_items = get_all_news(sym)
        news_score = compute_news_score(news_items)

        # Composite Weighted Score (40% Tech / 40% Fund / 15% Mom / 5% News)
        composite_score = (w_tech * tech_score) + (w_fund * fund_score) + (w_mom * mom_score) + (w_news * news_score)

        candidate_dataset.append({
            'symbol': sym,
            'price': price,
            'sector': yf_raw.get('info', {}).get('sector', 'N/A'),
            'fair_value': fair_val,
            'fair_value_method_note': fv_method_note,
            'mos_pct': mos_pct,
            'pe': fund_info['pe'],
            'pbv': fund_info['pbv'],
            'criteria_passed': row.get('criteria_passed', 4),
            'tech_score': round(tech_score, 1),
            'fund_score': round(fund_score, 1),
            'mom_score': round(mom_score, 1),
            'news_score': round(news_score, 1),
            'composite_score': round(composite_score, 1),
            'recent_news_count': len(news_items),
            'rvol': mom_data.get('rvol', 1.0),
            'vol_spike': mom_data.get('vol_spike', False)
        })

    # STAGE 5: AI LLM Synthesis / Fallback Ranking
    notify(5, 0, 100, "Stage 5/5: AI Model Generating Investment Thesis & Top 10 Ranking...")

    # Sort dataset by composite score descending
    candidate_dataset.sort(key=lambda x: x['composite_score'], reverse=True)

    top_10 = candidate_dataset[:10]

    api_key = os.environ.get("GEMINI_API_KEY")
    gemini_ai_output = None

    if api_key:
        gemini_ai_output = query_gemini_ai(top_10, api_key)

    gemini_map = {item['symbol']: item for item in (gemini_ai_output or [])}

    final_rankings = []
    for rank_idx, item in enumerate(top_10, 1):
        sym = item['symbol']
        ai_meta = gemini_map.get(sym, {})

        score = item['composite_score']
        grade = ai_meta.get('ai_grade')
        if not grade:
            if score >= 85:
                grade = "A+"
            elif score >= 75:
                grade = "A"
            elif score >= 65:
                grade = "B+"
            else:
                grade = "B"

        thesis = ai_meta.get('investment_thesis') or f"Solid overall setup for {sym} with strong valuation margin of safety ({item['mos_pct']}%) and technical oversold support."
        risks = ai_meta.get('key_risks') or f"General SET market volatility and sector cyclicality."

        final_rankings.append({
            "rank": rank_idx,
            "symbol": sym,
            "sector": item['sector'],
            "price": item['price'],
            "fair_value": item['fair_value'],
            "fair_value_method_note": item['fair_value_method_note'],
            "mos_pct": item['mos_pct'],
            "pe": item['pe'],
            "pbv": item['pbv'],
            "criteria_passed": item['criteria_passed'],
            "composite_score": item['composite_score'],
            "tech_score": item['tech_score'],
            "fund_score": item['fund_score'],
            "mom_score": item['mom_score'],
            "news_score": item['news_score'],
            "ai_grade": grade,
            "investment_thesis": thesis,
            "key_risks": risks,
            "rvol": item['rvol'],
            "vol_spike": item['vol_spike']
        })

    notify(5, 100, 100, "AI Top 10 Selection Completed Successfully.")

    return {
        "status": "success",
        "date": date_str,
        "set50_only": set50_only,
        "index_filter": index_filter,
        "weights": {
            "weight_tech": round(w_tech, 2),
            "weight_fund": round(w_fund, 2),
            "weight_mom": round(w_mom, 2),
            "weight_news": round(w_news, 2)
        },
        "total_screened": len(matched_stocks),
        "total_analyzed": total_candidates,
        "rankings": final_rankings,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
