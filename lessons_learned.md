# Lessons Learned: AI Stock Selection & Ranking Engine (v3.0 AI Edition)

## 1. Project Overview
- **Goal**: Develop an end-to-end AI Stock Selection Engine that automates technical screening, fundamental valuation, 30-day news aggregation, momentum volume checks, and selects the Top 10 Ranked stocks.
- **Architectural Requirement**: Master files in `Hybrid Investment/Web_base` must be kept completely untouched as reference master. All AI selection development is isolated in `Hybrid Investment/3_AI_Selection`.

---

## 2. Key Technical Discoveries & Solutions

### A. Isolated Workspace Strategy
- **Discovery**: Modifying production web apps directly introduces risk to existing user features.
- **Solution**: Created `3_AI_Selection` folder as a clean copy of `Web_base`. This guarantees 100% master file preservation while allowing full freedom for new AI features.

### B. Dynamic Scoring Weights & Weight Normalization
- **Discovery**: Different investors prioritize technical setups, fundamental valuation, momentum spikes, or news sentiment differently.
- **Solution**: Built an "AI Selection Guide" modal in the UI with interactive sliders allowing users to dynamically adjust weights (default: Technical 30%, Fundamental 40%, Momentum 20%, News 10%). The engine normalizes weights dynamically so the composite score is always scaled 0-100.

### C. Asynchronous Multi-Stage Progress Tracking
- **Discovery**: Deep analysis of fundamentals, news, and momentum for 25 candidate stocks takes ~20 seconds. Synchronous HTTP requests would cause browser timeout or server worker restart on cloud environments like Render.
- **Solution**: Implemented background thread processing in `screening_api.py` (`/api/ai_rank/start`, `/api/ai_rank/progress`, `/api/ai_rank/results`) with 5 stage indicators. The UI polls progress smoothly every 1000ms.

### D. LLM Synthesis & Fallback Resilience
- **Discovery**: Relying purely on external LLM APIs can result in failures if `GEMINI_API_KEY` is missing or network rate limits are reached.
- **Solution**: Designed a robust multi-factor quantitative scoring fallback engine. If `GEMINI_API_KEY` is provided, the engine queries Gemini to enhance investment thesis descriptions and risk analysis. If offline, the multi-factor scoring algorithm completes 100% of rankings and generates rule-based theses seamlessly.

### E. Screening Engine Data Structure Alignment
- **Discovery**: `run_screening()` in `screening_engine.py` groups output dictionaries under the key `'results'` with sub-keys `'6'`, `'5'`, `'4'`, etc., rather than a flat `'data'` array. Also, individual stock dictionaries use lowercase keys (`'symbol'`, `'close'`, `'rsi'`, `'stoch'`).
- **Solution**: Refactored candidate extraction in `ai_ranking_engine.py` to iterate through criteria keys `'6'` down to `'0'` and safely extract `'symbol'`, `'close'`, `'pe'`, and `'pbv'` with fallback logic.

### F. Intrinsic Valuation Dispatch Helper
- **Discovery**: `calc_forecast_metrics()` requires specific EPS and historical multiplier arguments derived from `yfinance` historical dictionary, whereas fair values for standard vs financial stocks require distinct DCF, DDM, PER, and PBV model dispatches.
- **Solution**: Created `compute_stock_valuation(yf_raw)` in `ai_ranking_engine.py` to handle sector-aware valuation dispatch (CAPM WACC DCF for industrial stocks vs Gordon DDM / Justified P/BV for financial stocks) aligned with `app.py` logic.

### G. Minimum 4 Criteria Technical Screening Threshold
- **Requirement**: Candidate stocks evaluated by the AI Stock Selection Engine must meet a strict minimum quality bar of passing **at least 4 technical criteria** (out of 6 criteria: C1-C6).
- **Solution**: Implemented `min_criteria=4` filtering in `ai_ranking_engine.py` (`valid_c_counts = ['6', '5', '4']`), ignoring low-tier technical setups (<4 criteria) and passing `min_criteria` parameter through the `/api/ai_rank/start` endpoint.

### H. Margin of Safety (MOS %) Parameter Order Verification
- **Discovery**: In `ai_ranking_engine.py`, `calc_margin_of_safety` was called with inverted positional arguments `calc_margin_of_safety(price, fair_val)`. Since `calc_margin_of_safety` definition expects `(fair_value, current_price)`, the engine computed `(Price - Fair Value) / Fair Value = -73.6%` (Discount %) instead of the true Margin of Safety `(Fair Value - Price) / Price = +279.1%`.
- **Solution**: Fixed argument order in `ai_ranking_engine.py` to `calc_margin_of_safety(fair_val, price)`. Now, stocks trading below Fair Value display a positive MOS % (undervaluation margin).

### J. Warren Buffett & Peter Lynch Fundamental Scoring Model (v5.0)
- **Requirement**: Upgrade Fundamental Scoring Engine based on classic value investing (Buffett: Margin of Safety, ROE, Net Margin, Balance Sheet Safety) and GARP principles (Peter Lynch: PEG Ratio, Dividend Yield, Free Cash Flow).
- **Solution**:
  1. Created proposal document `fundamental_scoring_proposal.md` detailing the 5-pillar fundamental scoring framework.
  2. Implemented 5 fundamental pillars in `ai_ranking_engine.py`:
     - **Pillar 1 (MOS & Intrinsic Valuation - Buffett, Max 30 pts)**: MOS $\ge +30\%$ (+30 pts), $\ge +15\%$ (+20 pts).
     - **Pillar 2 (Moat & Capital Efficiency - Buffett, Max 25 pts)**: ROE $\ge 20\%$ & Net Margin $\ge 12\%$ (+25 pts), ROE $\ge 15\%$ (+18 pts).
     - **Pillar 3 (GARP Valuation & PEG Ratio - Peter Lynch, Max 20 pts)**: PEG $\le 0.5$ (+20 pts), PEG $\le 0.8$ (+15 pts).
     - **Pillar 4 (Balance Sheet & Leverage - Buffett & Lynch, Max 15 pts)**: Debt/Equity $< 0.5$ (+15 pts), $\le 1.0$ (+10 pts).
     - **Pillar 5 (Shareholder Yield & FCF - Buffett & Lynch, Max 10 pts)**: Div Yield $\ge 4.0\%$ + Positive FCF (+10 pts).

### K. Target-Specific Button Loading State & Render.com Preparedness
- **Issue**: Clicking `SET50` or `SET100` buttons previously modified `btnRunAiRanking` ("Run AI Selection from SET") loading text due to shared element targeting.
- **Solution**:
  1. Updated `runAiSelection(indexFilter)` in `static/ai_ranking.js` to change `⌛ AI Analyzing…` text strictly on the clicked button (`btnRunSet50Ranking`, `btnRunSet100Ranking`, or `btnRunAiRanking`).
  2. Prepared `.gitignore`, `Procfile` (`gunicorn --worker-class gthread --threads 4 --timeout 300 app:app`), `runtime.txt` (`python-3.11.9`), `requirements.txt`, and deployment documentation in `README.md` for seamless GitHub and Render.com cloud deployment.

---

## 3. Best Practices & Guidelines for Future Updates
1. **Candidate Pool Management**: Offer full candidate screening, SET50, and SET100 index filter modes for optimal user flexibility.
2. **Shortlist Interoperability**: Stock cards in the AI Top 10 tab expose direct `+ Shortlist` actions, integrating smoothly with the global shortlist storage system.
3. **Cloud Deployment**: Keep `Procfile`, `requirements.txt`, and `runtime.txt` synchronized in project root for continuous integration on Render.com.





