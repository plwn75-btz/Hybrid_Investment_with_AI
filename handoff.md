# Handoff: AI Stock Selection & Ranking Engine (v5.0 AI Edition)

## 1. Executive Summary
- **Objective**: Build an automated, multi-stage AI Stock Selection Engine into a new independent project folder (`Hybrid Investment/3_AI_Selection`), preserving `Web_base` master codebase untouched.
- **Current Status**: **Completed & Verified (v4.0)**. `ai_ranking_engine.py`, `set50_list.py`, `screening_api.py`, `templates/index.html`, `static/screening.css`, and `static/ai_ranking.js` updated and tested.
- **Recipient Action**: Ready for deployment and execution. Can run locally via `python app.py` or test via `python test_ai_ranking.py`.

---

## 2. Context & Architectural Features (v4.0)

- **Environment**:
  - Workspace: `c:\Users\pipes\OneDrive\Documents\Google_AntiGravity\Project\Stock_Auto_Finding\Hybrid Investment\3_AI_Selection`
  - Master Backup: `Hybrid Investment\Web_base` (Unchanged)
  - Web Framework: Flask / Gunicorn.
- **Revised Default Scoring Weights**:
  - Technical Screening Weight: `40%` (0.40)
  - Fundamental Valuation Weight: `40%` (0.40)
  - Momentum & Volume Weight: `15%` (0.15) (`Momentum: 15%` chip label)
  - News & Sentiment Weight: `5%` (0.05)
- **SET Index Selection Buttons**:
  - Integrated official SET50 and SET100 constituent lists in [set50_list.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/set50_list.py).
  - Added 3 distinct execution buttons with target-specific loading state (`⌛ AI Analyzing…` displayed strictly on the clicked button):
    1. **"🎯 Run AI Selection from SET50"** (Restricts screening strictly to SET50 blue-chips)
    2. **"🏆 Run AI Selection from SET100"** (Restricts screening strictly to SET100 large/mid-caps)
    3. **"⚡ Run AI Selection from SET"** (Screens all SET stocks)
- **Dedicated Scoring Principles Tab (`📖 SCORING PRINCIPLES`)**:
  - Built interactive glassmorphic UI tab in [templates/index.html](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/templates/index.html) rendering comprehensive reference tables for Technical, Warren Buffett Value Moat, Peter Lynch GARP, Momentum, and News Sentiment scoring.
- **Fair Value Concept Notes & Technical Badge**:
  - Displays explicit note badges on stock cards (`💡 Fair Value Method: 10-Yr CAPM DCF Model`, `Bank Justified P/BV & DDM Model`, or `Relative PER & PBV Avg (DCF N/A)`).
  - Displays header badge statement: **`4/6 TECHNICAL CRITERIA PASSED`** (or `${stock.criteria_passed}/6 TECHNICAL CRITERIA PASSED`).
- **Technical Criteria Filtering & Prioritization**:
  - **Minimum Threshold**: Accepts stocks passing **ANY 4 or more criteria out of C1–C6** (`criteria_passed >= 4`).
  - **Priority Sorting**: Ranks candidate stocks passing 6 criteria first, then 5 criteria, then 4 criteria, with tiered technical score bonuses (+30 pts for 6, +20 pts for 5, +10 pts for 4).

---

## 3. Four Scoring Pillars Reference

### A. Technical Score (`compute_technical_score`)
- **Base Score**: 40.0 pts (Clamped 0–100).
- Criteria Bonus: 6/6 (+30.0 pts), 5/6 (+20.0 pts), 4/6 (+10.0 pts).
- RSI Reversal: $\le 35$ (+15.0 pts), $\le 45$ (+10.0 pts), $\ge 70$ (-10.0 pts).
- Stochastic Oscillator: $\le 30$ (+10.0 pts), $\ge 80$ (-5.0 pts).
- Trend Alignment: Price $\ge$ EMA200 (+5.0 pts).

### B. Fundamental Score (`compute_fundamental_score`) — *v5.0 Buffett & Peter Lynch Model*
- **Range**: `0 to 100` points across 5 core fundamental pillars:
  1. **Margin of Safety (Buffett, Max 30 pts)**: MOS $\ge +30\%$ (+30.0 pts), $\ge +15\%$ (+20.0 pts), $\ge 0\%$ (+10.0 pts), $< -20\%$ (-15.0 pts).
  2. **Capital Efficiency & Moat (Buffett, Max 25 pts)**: ROE $\ge 20\%$ & Net Margin $\ge 12\%$ (+25.0 pts), ROE $\ge 15\%$ (+18.0 pts), ROE $\ge 10\%$ (+10.0 pts), ROE $< 0\%$ (-15.0 pts).
  3. **GARP Valuation & PEG (Peter Lynch, Max 20 pts)**: PEG $\le 0.5$ (+20.0 pts), $\le 0.8$ (+15.0 pts), $\le 1.2$ (+8.0 pts), $> 2.0$ (-10.0 pts).
  4. **Balance Sheet & Leverage (Buffett & Lynch, Max 15 pts)**: Debt/Equity $< 0.5$ (+15.0 pts), $\le 1.0$ (+10.0 pts), $> 2.0$ (-10.0 pts).
  5. **Shareholder Yield & FCF (Buffett & Lynch, Max 10 pts)**: Div Yield $\ge 4.0\%$ + Positive FCF (+10.0 pts), Div Yield $\ge 2.0\%$ (+6.0 pts).

### C. Momentum Score (`compute_momentum_score`)
- **Base Score**: 50.0 pts (Clamped 0–100).
- Volume Surge: Sudden volume spike (+25.0 pts).
- Relative Volume (RVOL): $\ge 1.5$ (+15.0 pts), $\ge 1.2$ (+10.0 pts).
- Price Action: Daily change $> 0\%$ (+10.0 pts), $< -3.0\%$ (-10.0 pts).

### D. News Sentiment Score (`compute_news_score`)
- **Base Score**: 50.0 pts (Clamped 10–95).
- Scans headlines across 5 sources (yfinance, Google News, SET, Thunhoon, RYT9).
- Formula: $50.0 + (5.0 \times \text{Positive Hits}) - (5.0 \times \text{Negative Hits})$.

---

## 4. Progress Tracker & Completed Tasks
- [x] Create new isolated project folder `Hybrid Investment/3_AI_Selection` preserving master codebase.
- [x] Build multi-stage AI Stock Selection module [ai_ranking_engine.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/ai_ranking_engine.py).
- [x] Create SET50 & SET100 constituent list module [set50_list.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/set50_list.py).
- [x] Update Flask Blueprint endpoints in [screening_api.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/screening_api.py) (`/api/ai_rank/start`, `/api/ai_rank/progress`, `/api/ai_rank/results`).
- [x] Integrate **`🤖 AI TOP 10 RANKING`** tab, **"AI Selection Guide"** modal, and 3 AI selection buttons in [templates/index.html](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/templates/index.html).
- [x] Add glassmorphic CSS styling in [static/screening.css](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/static/screening.css) and client JS in [static/ai_ranking.js](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/static/ai_ranking.js).
- [x] Write integration test script [test_ai_ranking.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/test_ai_ranking.py).
- [x] Document project step execution in [handoff.md](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/handoff.md) and [lessons_learned.md](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/lessons_learned.md).

---

## 5. Key Files
- **[ai_ranking_engine.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/ai_ranking_engine.py)** - Core 5-stage AI Stock Selection Engine.
- **[set50_list.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/set50_list.py)** - Official SET50 & SET100 Index constituents list & helper functions.
- **[screening_api.py](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/screening_api.py)** - Flask Blueprint providing background AI analysis thread & polling endpoints.
- **[templates/index.html](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/templates/index.html)** - Dashboard template with AI TOP 10 tab, 3 AI Selection buttons, and AI Guide Modal.
- **[static/ai_ranking.js](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/static/ai_ranking.js)** - Frontend controller handling weight customization, index modes, card rendering, and shortlist addition.
- **[lessons_learned.md](file:///c:/Users/pipes/OneDrive/Documents/Google_AntiGravity/Project/Stock_Auto_Finding/Hybrid%20Investment/3_AI_Selection/lessons_learned.md)** - Documentation of architectural decisions and lessons learned.

---

## 6. How to Resume & Deploy to GitHub / Render.com

### Local Development:
1. Open terminal in workspace: `c:\Users\pipes\OneDrive\Documents\Google_AntiGravity\Project\Stock_Auto_Finding\Hybrid Investment\3_AI_Selection`.
2. Run `python app.py` to start local dashboard. Open `http://localhost:5000`.

### Cloud Deployment to Render.com:
1. All deployment configuration files (`Procfile`, `requirements.txt`, `runtime.txt`, `.gitignore`, `README.md`) are created and ready in `Hybrid Investment/3_AI_Selection`.
2. Push repository to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Deploy v5.0 AI Edition with Buffett & Lynch Fundamental Engine"
   git remote add origin https://github.com/YOUR_USERNAME/SET_AI_Selection.git
   git push -u origin main
   ```
3. Connect repository on [Render.com](https://dashboard.render.com/) as a **Web Service**:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class gthread --threads 4 --timeout 300 app:app`
