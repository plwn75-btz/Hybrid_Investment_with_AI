/**
 * ai_ranking.js — AI Stock Selection Frontend Controller (v6.0)
 * Weights: Technical 30% / Fundamental 40% / Momentum 15% / News 5% / Dividend 10%
 */

// ── Default Weights ───────────────────────────────────────────────────────────
const AI_DEFAULT_WEIGHTS = {
  weight_tech: 30,
  weight_fund: 40,
  weight_mom:  15,
  weight_news:  5,
  weight_div:  10
};

let aiPollTimer = null;
let currentIndexFilter = 'set50'; // default

// ── Initialise on DOM ready ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initWeightSliders();
  bindAiButtons();
});

// ── Weight Sliders ────────────────────────────────────────────────────────────
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
    });
  });
  recalcWeightTotal();
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

// ── Button Binding ────────────────────────────────────────────────────────────
function bindAiButtons() {
  const btnSet50  = document.getElementById('btnRunSet50Ranking');
  const btnSet100 = document.getElementById('btnRunSet100Ranking');
  const btnAll    = document.getElementById('btnRunAiRanking');

  if (btnSet50)  btnSet50.addEventListener('click',  () => runAiSelection('set50',  btnSet50));
  if (btnSet100) btnSet100.addEventListener('click', () => runAiSelection('set100', btnSet100));
  if (btnAll)    btnAll.addEventListener('click',    () => runAiSelection('all',    btnAll));
}

// ── Run AI Selection ──────────────────────────────────────────────────────────
function runAiSelection(indexFilter, clickedBtn) {
  currentIndexFilter = indexFilter;

  // Disable all AI buttons, set loading text only on clicked button
  ['btnRunSet50Ranking','btnRunSet100Ranking','btnRunAiRanking'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = true;
  });
  if (clickedBtn) {
    clickedBtn._originalText = clickedBtn.innerHTML;
    clickedBtn.innerHTML = '⌛ AI Analyzing…';
  }

  // Clear previous results
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

// ── Poll Progress ─────────────────────────────────────────────────────────────
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

// ── Reset Buttons ─────────────────────────────────────────────────────────────
function resetAiButtons(clickedBtn) {
  ['btnRunSet50Ranking','btnRunSet100Ranking','btnRunAiRanking'].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });
  if (clickedBtn && clickedBtn._originalText) {
    clickedBtn.innerHTML = clickedBtn._originalText;
  }
}

// ── Progress UI ───────────────────────────────────────────────────────────────
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

// ── Render Results ────────────────────────────────────────────────────────────
function renderAiResults(data) {
  const container = document.getElementById('aiRankingResults');
  if (!container) return;

  const rankings = data.rankings || [];
  if (!rankings.length) {
    container.innerHTML = `<div class="ai-empty">No stocks matched the AI selection criteria for the selected index and date.</div>`;
    return;
  }

  const idxLabel = { all: 'Full SET', set50: 'SET50', set100: 'SET100' }[data.index_filter] || 'SET';
  const w = data.weights || {};

  // Header summary
  let html = `
    <div class="ai-results-header">
      <div class="ai-results-title">🤖 AI TOP ${rankings.length} — ${idxLabel} Index</div>
      <div class="ai-weight-chips">
        <span class="ai-chip tech">Tech ${Math.round((w.weight_tech||0)*100)}%</span>
        <span class="ai-chip fund">Fund ${Math.round((w.weight_fund||0)*100)}%</span>
        <span class="ai-chip mom">Mom ${Math.round((w.weight_mom||0)*100)}%</span>
        <span class="ai-chip news">News ${Math.round((w.weight_news||0)*100)}%</span>
        <span class="ai-chip div">Div ${Math.round((w.weight_div||0)*100)}%</span>
      </div>
      <div class="ai-meta">📅 ${data.date} &nbsp;|&nbsp; 🔍 Screened ${data.total_screened} stocks &nbsp;|&nbsp; 🧮 Analyzed ${data.total_analyzed}</div>
    </div>
    <div class="ai-cards-grid">
  `;

  rankings.forEach(stock => {
    const gradeClass = {
      'A+': 'grade-aplus', 'A': 'grade-a', 'A-': 'grade-aminus',
      'B+': 'grade-bplus', 'B': 'grade-b'
    }[stock.ai_grade] || 'grade-b';

    const mosBadge = stock.mos_pct > 0
      ? `<span class="badge badge-green">MOS +${stock.mos_pct.toFixed(1)}%</span>`
      : `<span class="badge badge-red">MOS ${stock.mos_pct.toFixed(1)}%</span>`;

    const divYieldPct = stock.div_yield > 0
      ? (stock.div_yield < 1 ? (stock.div_yield * 100).toFixed(2) : stock.div_yield.toFixed(2))
      : '0.00';

    const spikeTag = stock.vol_spike ? `<span class="badge badge-orange">🔥 Vol Spike</span>` : '';
    const criteriaTag = `<span class="badge badge-blue">${stock.criteria_passed}/6 CRITERIA</span>`;
    const fvNote = stock.fair_value_method_note
      ? `<div class="ai-fv-note">💡 ${stock.fair_value_method_note}</div>` : '';

    html += `
      <div class="ai-card" id="aiCard_${stock.symbol}">
        <div class="ai-card-header">
          <div class="ai-rank-badge">#${stock.rank}</div>
          <div class="ai-card-symbol">${stock.symbol}</div>
          <div class="ai-grade ${gradeClass}">${stock.ai_grade}</div>
        </div>

        <div class="ai-card-sector">${stock.sector || '—'}</div>
        <div class="ai-card-tags">${criteriaTag} ${mosBadge} ${spikeTag}</div>
        ${fvNote}

        <div class="ai-card-metrics">
          <div class="ai-metric">
            <span class="ai-metric-label">Price</span>
            <span class="ai-metric-value">฿${stock.price ? stock.price.toFixed(2) : '—'}</span>
          </div>
          <div class="ai-metric">
            <span class="ai-metric-label">Fair Value</span>
            <span class="ai-metric-value">฿${stock.fair_value ? stock.fair_value.toFixed(2) : '—'}</span>
          </div>
          <div class="ai-metric">
            <span class="ai-metric-label">P/E</span>
            <span class="ai-metric-value">${stock.pe ? stock.pe.toFixed(1) : '—'}</span>
          </div>
          <div class="ai-metric">
            <span class="ai-metric-label">P/BV</span>
            <span class="ai-metric-value">${stock.pbv ? stock.pbv.toFixed(2) : '—'}</span>
          </div>
          <div class="ai-metric">
            <span class="ai-metric-label">Div Yield</span>
            <span class="ai-metric-value ai-div-yield">${divYieldPct}%</span>
          </div>
          <div class="ai-metric">
            <span class="ai-metric-label">RVOL</span>
            <span class="ai-metric-value">${stock.rvol ? stock.rvol.toFixed(2) : '—'}x</span>
          </div>
        </div>

        <div class="ai-score-bars">
          ${scoreBar('Technical', stock.tech_score, '#6366f1')}
          ${scoreBar('Fundamental', stock.fund_score, '#22c55e')}
          ${scoreBar('Momentum', stock.mom_score, '#f59e0b')}
          ${scoreBar('News', stock.news_score, '#06b6d4')}
          ${scoreBar('Dividend', stock.div_score, '#ec4899')}
          ${scoreBar('COMPOSITE', stock.composite_score, '#a855f7', true)}
        </div>

        <div class="ai-thesis">
          <div class="ai-thesis-label">📊 Investment Thesis</div>
          <div class="ai-thesis-text">${stock.investment_thesis || '—'}</div>
        </div>
        <div class="ai-risks">
          <div class="ai-risks-label">⚠️ Key Risk</div>
          <div class="ai-risks-text">${stock.key_risks || '—'}</div>
        </div>

        <div class="ai-card-actions">
          <button class="btn-shortlist-ai" onclick="addAiStockToShortlist('${stock.symbol}')">
            ＋ Shortlist
          </button>
          <button class="btn-view-ai" onclick="loadStockFromAI('${stock.symbol}')">
            📈 View
          </button>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;
}

function scoreBar(label, value, color, isBold) {
  const pct = Math.min(100, Math.max(0, value || 0));
  const boldStyle = isBold ? 'font-weight:700;' : '';
  return `
    <div class="ai-score-bar-row">
      <span class="ai-score-bar-label" style="${boldStyle}">${label}</span>
      <div class="ai-score-bar-track">
        <div class="ai-score-bar-fill" style="width:${pct}%;background:${color};"></div>
      </div>
      <span class="ai-score-bar-val" style="${boldStyle}">${pct.toFixed(1)}</span>
    </div>
  `;
}

// ── Shortlist & View integration ──────────────────────────────────────────────
function addAiStockToShortlist(symbol) {
  if (typeof addToShortList === 'function') {
    addToShortList(symbol);
  } else {
    // Trigger valuation load then shortlist
    const symInput = document.getElementById('symbolInput');
    if (symInput) symInput.value = symbol;
    alert(`Load ${symbol} in the Valuation tab first, then click SHORT LIST.`);
  }
}

function loadStockFromAI(symbol) {
  const symInput = document.getElementById('symbolInput');
  if (symInput) symInput.value = symbol;
  // Switch to valuation tab and run
  const valTab = document.querySelector('[data-tab="valuation"]');
  if (valTab) valTab.click();
  const runBtn = document.getElementById('btnFetch');
  if (runBtn) setTimeout(() => runBtn.click(), 300);
}

// ── Error Display ─────────────────────────────────────────────────────────────
function showAiError(msg) {
  const el = document.getElementById('aiRankingResults');
  if (el) el.innerHTML = `<div class="ai-error">❌ ${msg}</div>`;
}
