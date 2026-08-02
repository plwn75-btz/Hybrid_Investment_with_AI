# HYBRID INVESTMENT – BTZ Inc. Ver. 5.0 (2026 AI Edition)

An automated, multi-dimensional AI Stock Selection, Screening, and Intrinsic Valuation Web Application for SET-listed stocks.

---

## 🌟 Key Features (v5.0 AI Edition)

- **🤖 AI Top 10 Selection Engine**: 5-stage multi-factor stock ranking (Technical 40% / Fundamental 40% / Momentum 15% / News 5%).
- **⚖️ Warren Buffett & Peter Lynch Fundamental Model (v5.0)**:
  1. *Pillar 1*: Intrinsic Margin of Safety (DCF / Justified P/BV / DDM vs Market Price).
  2. *Pillar 2*: Economic Moats & ROE Profitability ($\text{ROE} \ge 20\%$, Net Margin $\ge 12\%$).
  3. *Pillar 3*: Peter Lynch GARP & PEG Ratio ($\text{PEG} \le 0.5$ Bargain Hunter).
  4. *Pillar 4*: Balance Sheet Safety & Debt-to-Equity ($\text{D/E} < 0.5$).
  5. *Pillar 5*: Shareholder Yield & Free Cash Flow ($\text{Yield} \ge 4.0\%$ + FCF).
- **🎯 Quick Selection Buttons**:
  - `🎯 Run AI Selection from SET50` (Blue-chip index filter)
  - `🏆 Run AI Selection from SET100` (Large & mid-cap index filter)
  - `⚡ Run AI Selection from SET` (Full SET candidate screening)
- **📖 Interactive Scoring Principles Tab**: Live UI reference guide detailing exact scoring rules and formulas.
- **📰 30-Day News Aggregator**: Multi-source news scanner (*yfinance*, *Google News*, *SET Announcements*, *Thunhoon*, *RYT9*).

---

## 📁 Repository Structure

```
├── app.py                      # Main Flask application & Gunicorn entry point
├── ai_ranking_engine.py        # Core 5-stage AI Stock Selection Engine
├── set50_list.py               # Official SET50 & SET100 constituent lists
├── screening_api.py            # Flask API Blueprint for AI background worker & progress polling
├── valuation_engine.py        # Intrinsic valuation algorithms (DCF, DDM, PER, PBV)
├── screening_engine.py        # Technical screening engine (C1-C6 criteria)
├── data_fetcher.py            # Central data hub (yfinance, SET data)
├── news_fetcher.py             # 5-source financial news aggregator
├── test_ai_ranking.py          # Automated integration test script
├── handoff.md                  # Comprehensive handoff & architecture report
├── lessons_learned.md          # Key architectural learnings & bug fix log
├── templates/
│   └── index.html              # Modern dark glassmorphic dashboard UI
├── static/
│   ├── ai_ranking.js           # AI ranking controller & button event handlers
│   ├── app.js                  # Valuation controller & tab navigator
│   ├── screening.js            # Screening tab logic
│   └── screening.css           # Custom glassmorphic styling
├── Procfile                    # Render.com web process configuration
├── requirements.txt            # Python dependencies
├── runtime.txt                 # Python version specification (3.11.9)
└── .gitignore                  # Git exclusion rules
```

---

## 🚀 Local Execution Instructions

1. Clone or navigate to directory:
   ```bash
   cd "Hybrid Investment/3_AI_Selection"
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run local server:
   ```bash
   python app.py
   ```
4. Open browser at `http://localhost:5000` (or `http://localhost:5101`).

---

## ☁️ Deployment Guide for Render.com & GitHub

### Step 1: Push Code to GitHub
1. Initialize Git repository (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Deploy v5.0 AI Edition with Buffett & Lynch Fundamental Model"
   ```
2. Create repository on GitHub and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/SET_AI_Selection.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Create Web Service on Render.com
1. Log in to [Render.com Dashboard](https://dashboard.render.com/).
2. Click **New +** $\rightarrow$ **Web Service**.
3. Connect your GitHub repository (`SET_AI_Selection`).
4. Configure service settings:
   - **Name**: `set-ai-selection`
   - **Environment**: `Python 3`
   - **Region**: Singapore (or nearest region)
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class gthread --threads 4 --timeout 300 app:app`
5. *(Optional)* Add Environment Variable:
   - `GEMINI_API_KEY`: *(Your Google Gemini API Key for AI synthesis text)*
6. Click **Create Web Service**. Deploy complete!
