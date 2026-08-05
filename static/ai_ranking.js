/**
 * ai_ranking.js — AI Stock Selection Frontend Controller (v6.0 - Precise Design Match)
 */

const AI_DEFAULT_WEIGHTS = {
  weight_tech: 30,
  weight_fund: 40,
  weight_mom:  15,
  weight_news:  5,
  weight_div:  10
};

let aiPollTimer = null;
let currentIndexFilter = 'set50';

document.addEventListener('DOMContentLoaded', () => {
  initWeightSliders();
  bindAiButtons();
});

function toggleWeightModal() {
  const panel = document.getElementById('aiWeightPanel');
  if (panel) {
    panel.style.display = (panel.style.display === 'none' || !panel.style.display) ? 'block' : 'none';
  }
}

function initWeightSliders() {
  const keys = ['tech', 'fund', 'mom', 'news', 'div'];
  keys.forEach(k => {
    const slider = document.getElementById(`aiWeight_${k}`);
    const label  = document.getElementById(`aiWeightVal_${k}`);
    if (!slider || !label) return;
    slider.value = AI_DEFAULT_WEIGHTS[`weight_${k}`];
    label.textContent = slider.value + '%';
    slider.addEventListener('input', () => {
      label.textContent = slider.value + '%';
      recalcWeightTotal();
      updateBannerChips();
    });
  });
  recalcWeightTotal();
  updateBannerChips();
}

function updateBannerChips() {
  ['tech', 'fund', 'mom', 'news', 'div'].forEach(k => {
    const slider = document.getElementById(`aiWeight_${k}`);
    const chipVal = document.getElementById(`chip${k.charAt(0).toUpperCase() + k.slice(1)}Val`);
    if (slider && chipVal) chipVal.textContent = slider.value + '%';
  });
}

function recalcWeightTotal() {
  const keys = ['tech', 'fund', 'mom', 'news', 'div'];
  const total = keys.reduce((s, k) => {
    const el = document.getElementById(`aiWeight_${k}`);
    return s + (el ? parseInt(el.value) : 0);
  }, 0);
  const totalEl = document.getElementById('aiWeightTotal');
  if (totalEl) {
    totalEl.textContent = total + '%';
    totalEl.style.color = total === 100 ? '#22c55e' : '#ef4444';
  }
}

function getWeights() {
  const keys = ['tech', 'fund', 'mom', 'news', 'div'];
  const raw = {};
  keys.forEach(k => {
    const el = document.getElementById(`aiWeight_${k}`);
    raw[`weight_${k}`] = el ? parseInt(el.value) / 100.0 : AI_DEFAULT_WEIGHTS[`weight_${k}`] / 100.0;
  });
  return raw;
}

function bindAiButtons() {
  const btnSet50  = document.getElementById('btnRunSet50Ranking');
  const btnSet100 = document.getElementById('btnRunSet100Ranking');
  const btnAll    = document.getElementById('btnRunAiRanking');

  if (btnSet50)  btnSet50.addEventListener('click',  () => runAiSelection('set50',  btnSet50));
  if (btnSet100) btnSet100.addEventListener('click', () => runAiSelection('set100', btnSet100));
  if (btnAll)    btnAll.addEventListener('click',    () => runAiSelection('all',    btnAll));
}

function runAiSelection(indexFilter, clickedBtn) {
  currentIndexFilter = indexFilter;

  ['btnRunSet50Ranking','btnRunSet100Ranking','btnRunAiRanking'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = true;
  });
  if (clickedBtn) {
    clickedBtn._originalText = clickedBtn.innerHTML;
    clickedBtn.innerHTML = '⌛ AI Analyzing…';
  }

  const resultsEl = document.getElementById('aiRankingResults');
  if (resultsEl) resultsEl.innerHTML = '';
  showAiProgress(true);
  updateAiProgressBar(0, 'Initializing AI Analysis Pipeline…', 1);

  const weights = getWeights();
  const dateEl = document.getElementById('dateInput');
  const rsiEl  = document.getElementById('rsiInput');
  const stochEl = document.getElementById('stochInput');

  const payload = {
    ...weights,
    index_filter: indexFilter,
    date: dateEl ? dateEl.value : '',
    rsi: rsiEl ? parseInt(rsiEl.value) : 30,
    stoch: stochEl ? parseInt(stochEl.value) : 70,
    min_criteria: 4,
    process_all: true
  };

  fetch('/api/ai_rank/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) {
      showAiError(data.error);
      resetAiButtons(clickedBtn);
      return;
    }
    aiPollTimer = setInterval(() => pollAiProgress(clickedBtn), 1000);
  })
  .catch(err => {
    showAiError('Failed to start AI analysis: ' + err);
    resetAiButtons(clickedBtn);
  });
}

function pollAiProgress(clickedBtn) {
  fetch('/api/ai_rank/progress')
    .then(r => r.json())
    .then(data => {
      updateAiProgressBar(data.pct, data.message, data.stage);
      if (data.done) {
        clearInterval(aiPollTimer);
        fetchAiResults(clickedBtn);
      }
    })
    .catch(() => clearInterval(aiPollTimer));
}

function fetchAiResults(clickedBtn) {
  fetch('/api/ai_rank/results')
    .then(r => r.json())
    .then(data => {
      showAiProgress(false);
      resetAiButtons(clickedBtn);
      if (data.status === 'error') {
        showAiError(data.message || 'Unknown error');
      } else {
        renderAiResults(data);
      }
    })
    .catch(err => {
      showAiProgress(false);
      resetAiButtons(clickedBtn);
      showAiError('Failed to fetch results: ' + err);
    });
}

function resetAiButtons(clickedBtn) {
  ['btnRunSet50Ranking','btnRunSet100Ranking','btnRunAiRanking'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });
  if (clickedBtn && clickedBtn._originalText) {
    clickedBtn.innerHTML = clickedBtn._originalText;
  }
}

function showAiProgress(show) {
  const el = document.getElementById('aiProgressSection');
  if (el) el.style.display = show ? 'block' : 'none';
}

function updateAiProgressBar(pct, msg, stage) {
  const bar  = document.getElementById('aiProgressBar');
  const txt  = document.getElementById('aiProgressText');
  const stag = document.getElementById('aiProgressStage');
  if (bar)  bar.style.width = pct + '%';
  if (txt)  txt.textContent = msg || '';
  if (stag) stag.textContent = `Stage ${stage || 1}/5`;
}

function renderAiResults(data) {
  const container = document.getElementById('aiRankingResults');
  if (!container) return;

  const rankings = data.rankings || [];
  if (!rankings.length) {
    container.innerHTML = `<div class="ai-empty">No stocks matched the AI selection criteria for the selected index and date.</div>`;
    return;
  }

  let html = `<div class="ai-cards-grid">`;

  rankings.forEach(stock => {
    const mosClass = stock.mos_pct >= 0 ? 'mos-positive' : 'mos-negative';
    const mosText  = stock.mos_pct >= 0 ? `+${stock.mos_pct.toFixed(1)}%` : `${stock.mos_pct.toFixed(1)}%`;

    const fvNote = stock.fair_value_method_note || '10-Yr CAPM DCF Model';

    html += `
      <div class="ai-card" id="aiCard_${stock.symbol}">
        <!-- Top Row: Rank Circle, Symbol & Technical Criteria, Score & Grade -->
        <div class="ai-card-top">
          <div class="ai-rank-circle">#${stock.rank}</div>
          <div class="ai-symbol-block">
            <div class="ai-symbol-name">${stock.symbol}</div>
            <div class="ai-criteria-tag">N/A • ${stock.criteria_passed}/6 TECHNICAL CRITERIA PASSED</div>
          </div>
          <div class="ai-score-block">
            <div class="ai-score-num">${stock.composite_score.toFixed(1)}</div>
            <div class="ai-grade-badge">${stock.ai_grade || 'B'}</div>
          </div>
        </div>

        <!-- Metric Cards 4-Column Grid -->
        <div class="ai-metrics-grid">
          <div class="ai-metric-box">
            <div class="ai-metric-lbl">PRICE</div>
            <div class="ai-metric-val">฿${stock.price ? stock.price.toFixed(2) : '0.00'}</div>
          </div>
          <div class="ai-metric-box">
            <div class="ai-metric-lbl">FAIR VALUE</div>
            <div class="ai-metric-val">฿${stock.fair_value ? stock.fair_value.toFixed(2) : '0.00'}</div>
          </div>
          <div class="ai-metric-box">
            <div class="ai-metric-lbl">MOS %</div>
            <div class="ai-metric-val ${mosClass}">${mosText}</div>
          </div>
          <div class="ai-metric-box">
            <div class="ai-metric-lbl">P/E</div>
            <div class="ai-metric-val">${stock.pe ? stock.pe.toFixed(1) : '0.0'}</div>
          </div>
        </div>

        <!-- Fair Value Method Tag -->
        <div class="ai-fv-tag">
          💡 Fair Value Method: <span>${fvNote}</span>
        </div>

        <!-- Investment Thesis Box -->
        <div class="ai-box ai-thesis-box">
          <div class="ai-box-title">💡 AI Investment Thesis:</div>
          <div class="ai-box-body">${stock.investment_thesis || 'Solid overall setup with strong valuation margin of safety.'}</div>
        </div>

        <!-- Key Risk Factor Box -->
        <div class="ai-box ai-risk-box">
          <div class="ai-box-title">⚠️ Key Risk Factor:</div>
          <div class="ai-box-body">${stock.key_risks || 'General SET market volatility and sector cyclicality.'}</div>
        </div>

        <!-- Bottom Bar: Scores Breakdown + Shortlist Button -->
        <div class="ai-card-footer">
          <div class="ai-footer-scores">
            Tech: ${Math.round(stock.tech_score)} | Fund: ${Math.round(stock.fund_score)} | Mom: ${Math.round(stock.mom_score)} | News: ${Math.round(stock.news_score)} | Div: ${Math.round(stock.div_score || 50)}
          </div>
          <button class="btn-shortlist-pill" onclick="addAiStockToShortlist('${stock.symbol}')">
            + Shortlist
          </button>
        </div>

      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;
}

function addAiStockToShortlist(symbol) {
  if (typeof addToShortList === 'function') {
    addToShortList(symbol);
  } else {
    const symInput = document.getElementById('symbolInput');
    if (symInput) symInput.value = symbol;
    alert(`Added ${symbol} to shortlist.`);
  }
}

function showAiError(msg) {
  const el = document.getElementById('aiRankingResults');
  if (el) el.innerHTML = `<div class="ai-error">❌ ${msg}</div>`;
}
