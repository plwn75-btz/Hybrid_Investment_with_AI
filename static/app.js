/* app.js – Frontend logic for INTRINSIC VALUATION web app (v3) */
'use strict';

let currentResult = null;
let currentNews = [];
let currentNewsFilter = 'all';

// Bond yield source tag color coding
function updateBondSourceTag(sourceText) {
  const tag = document.getElementById('bondSourceTag');
  if (!tag) return;
  if (sourceText) tag.textContent = sourceText;
  const text = tag.textContent.toLowerCase();
  tag.classList.remove('source-live', 'source-fallback');
  if (text.includes('thaibma') && text.includes('live')) {
    tag.classList.add('source-live');
  } else if (text.includes('fallback') || text.includes('offline')) {
    tag.classList.add('source-fallback');
  }
  // yfinance keeps default cyan styling (no extra class needed)
}
// Apply on page load
document.addEventListener('DOMContentLoaded', () => updateBondSourceTag());

// ============================================================ Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
  });
});

// ============================================================ Symbol input
document.getElementById('symbolInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') runValuation();
});

// ============================================================ Formatting helpers
const fmt  = (v, dec=2) => v != null ? (+v).toFixed(dec) : '—';
const fmtP = (v) => v != null ? (+v).toFixed(1) + '%' : '—';
const fmtC = (v, dec=2) => v != null ? Number(v).toLocaleString('en-US', {minimumFractionDigits:dec, maximumFractionDigits:dec}) : '—';
const fmtVol = (v) => v != null ? Number(v).toLocaleString('en-US', {maximumFractionDigits:0}) : '—';
const fmtMOS = (v) => { if (v == null) return '—'; return (v >= 0 ? '+' : '') + (+v).toFixed(1) + '%'; };

// ============================================================ Run Valuation
async function runValuation() {
  const symbol = document.getElementById('symbolInput').value.trim().toUpperCase();
  if (!symbol) { setStatus('Please enter a stock symbol (e.g. AAV, PTT, CPALL)', 'error'); return; }

  const saleGrowth   = parseFloat(document.getElementById('saleGrowth').value)  || 5;
  const bondYield    = parseFloat(document.getElementById('bondYield').value)   || 3.0;
  const perBenchmark = parseFloat(document.getElementById('perBenchmark').value)|| 15;
  const pbvBenchmark = parseFloat(document.getElementById('pbvBenchmark').value)|| 1.5;

  showLoading(true);
  setStatus(`Fetching data for ${symbol} …`, 'loading');
  document.getElementById('assume-growth').textContent = saleGrowth.toFixed(1) + '%';

  try {
    const resp = await fetch('/api/valuate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, sale_growth: saleGrowth, bond_yield: bondYield,
        per_benchmark: perBenchmark, pbv_benchmark: pbvBenchmark })
    });
    const data = await resp.json();
    showLoading(false);
    if (!resp.ok || data.error) { setStatus('❌ ' + (data.error || 'Unknown error'), 'error'); return; }

    currentResult = { ...data, symbol, sale_growth: saleGrowth, timestamp: new Date().toLocaleString() };
    renderResult(data, saleGrowth);
    setStatus(`✅ Valuation complete for ${symbol} – ${data.company_name || ''}`, 'success');

    // Auto-fetch momentum & news in background
    fetchMomentum(symbol);
    fetchNews(symbol);
    fetchAndRenderValTechChart(symbol);
  } catch (err) {
    showLoading(false);
    setStatus('❌ Network error: ' + err.message, 'error');
  }
}

// ============================================================ Render Result
function renderResult(d, saleGrowth) {
  set('val-company', d.company_name || '—');
  set('val-price', fmt(d.price));
  set('val-hi', fmt(d.hi_52wk));
  set('val-lo', fmt(d.lo_52wk));
  set('companyNameShort', d.company_name || '—');
  set('companyFull', d.company_full || '—');
  set('companySector', d.sector || '—');
  set('sectorDisplay', d.sector || '—');
  set('waccDisplay', d.wacc_pct ? d.wacc_pct.toFixed(1) + '%' : '—');
  set('sharesDisplay', d.shares_m != null ? fmtC(d.shares_m, 2) + ' M' : '—');
  set('mktCapDisplay', d.market_cap_m != null ? fmtC(d.market_cap_m, 2) + ' MB' : '—');

  const website = d.website || '#';
  const wLink = document.getElementById('websiteLink');
  wLink.href = website.startsWith('http') ? website : '#';
  wLink.textContent = website.startsWith('http') ? 'Company Website ↗' : 'Website N/A';

  // Analyst Consensus Link
  const symbol = d.symbol || '';
  const cLink = document.getElementById('consensusLink');
  if (cLink) {
    if (symbol) {
      cLink.href = `https://www.settrade.com/th/equities/quote/${symbol}/analyst-consensus`;
      cLink.style.display = 'inline-block';
    } else {
      cLink.style.display = 'none';
    }
  }

  // Fair value labels
  const labels = d.fv_labels || {};
  const labelDCF = document.getElementById('label-fv-dcf');
  const labelDIV = document.getElementById('label-fv-div');
  const labelDDM = document.getElementById('label-fv-ddm');
  if (labelDCF) labelDCF.textContent = labels.dcf || 'FAIR VALUE (DCF)';
  if (labelDIV) labelDIV.textContent = labels.div ? `FAIR VALUE (${labels.div})` : 'FAIR VALUE (DIV.)';
  if (labelDDM) labelDDM.textContent = labels.ddm ? `FAIR VALUE (${labels.ddm})` : 'FAIR VALUE (DDM)';

  setFV('fv-dcf', 'mos-dcf', d.fv_dcf, d.mos_dcf);
  setFV('fv-div', 'mos-div', d.fv_div, d.mos_div);
  setFV('fv-ddm', 'mos-ddm', d.fv_ddm, d.mos_ddm);
  setFV('fv-per', 'mos-per', d.fv_per, d.mos_per);
  setFV('fv-pbv', 'mos-pbv', d.fv_pbv, d.mos_pbv);

  set('sens-min', d.sens_min != null ? fmt(d.sens_min) : '—');
  set('sens-max', d.sens_max != null ? fmt(d.sens_max) : '—');

  const fc = d.forecast || {};
  set('mv-fyield', fc.forecast_yield != null ? fmtP(fc.forecast_yield) : '—');
  set('mv-epsg', fc.yoy_eps_growth != null ? fmtP(fc.yoy_eps_growth) : '—');

  setMetric('m-pe','mv-pe',d.pe,'pe',fmt(d.pe));
  setMetric('m-pbv','mv-pbv',d.pbv,'pbv',fmt(d.pbv));
  setMetric('m-peg','mv-peg',d.peg,'peg',fmt(d.peg));
  setMetric(null,'mv-ebitda',d.ebitda,null,d.ebitda!=null?fmtC(d.ebitda,0)+' MB':'—');
  setMetric('m-eps','mv-eps',d.eps,null,fmt(d.eps));
  setMetric('m-de','mv-de',d.de,'de',fmt(d.de));
  setMetric(null,'mv-ev',d.ev,null,d.ev!=null?fmtC(d.ev,0)+' MB':'—');
  setMetric(null,'mv-eveb',d.ev_ebitda,null,fmt(d.ev_ebitda));
  setMetric('m-roa','mv-roa',d.roa,'rotc',fmtP(d.roa));
  setMetric(null,'mv-dps',d.dps,null,fmt(d.dps,4));
  setMetric(null,'mv-payout',d.payout,null,fmtP(d.payout));
  setMetric('m-gpm','mv-gpm',d.gpm,'npm',fmtP(d.gpm));
  setMetric(null,'mv-ebit',null,null,d.ebit_margin?fmtP(d.ebit_margin):'—');
  setMetric('m-saleg','mv-saleg',saleGrowth,'sale_growth',fmtP(saleGrowth));
  setMetric('m-ps','mv-ps',d.ps,'ps',fmt(d.ps));
  setMetric('m-rotc','mv-rotc',d.roa,'rotc',fmtP(d.roa));
  setMetric('m-roic','mv-roic',d.roe,'roic',fmtP(d.roe));
  setMetric('m-mktrev','mv-mktrev',d.mktcap_rev,'mktcap_rev',fmt(d.mktcap_rev));

  const colors = d.colors || {};
  applyColorMap(colors);

  const dp = d.dupont || {};
  set('dp-npm', dp.npm_pct != null ? dp.npm_pct.toFixed(1) + '%' : '—');
  set('dp-at', dp.asset_turnover != null ? (+dp.asset_turnover).toFixed(2) : '—');
  set('dp-fl', dp.financial_leverage != null ? (+dp.financial_leverage).toFixed(2) : '—');
  set('dp-roe', dp.roe_pct != null ? dp.roe_pct.toFixed(1) + '%' : '—');

  set('highlightBox', d.highlight || '—');
  set('dividendPolicyBox', d.dividend_policy || '—');
  set('lastXdDateBox', d.last_xd_date || 'N/A');
  set('xdDateBox', d.upcoming_xd_date || 'N/A');
  set('ft-eps', fc.forecast_eps != null ? fmt(fc.forecast_eps) + ' THB' : '—');
  set('ft-price', fc.forecast_price != null ? fmt(fc.forecast_price) + ' THB' : '—');
  set('ft-mos', fc.forecast_price_margin != null ? fmtP(fc.forecast_price_margin) : '—');
  set('ft-dps', fc.forecast_dps != null ? fmt(fc.forecast_dps, 2) + ' THB' : '—');
  set('ft-yield', fc.forecast_yield != null ? fmtP(fc.forecast_yield) : '—');
  set('ft-epsG', fc.yoy_eps_growth != null ? fmtP(fc.yoy_eps_growth) : '—');

  // Store chart data globally for toggling
  window.currentFinData = {
    annual: d.financial_history || [],
    quarterly: d.quarterly_history || []
  };

  // Render Financial Charts (default to annual)
  if (d.financial_history) {
    switchFinView('annual');
  }
}

function switchFinView(viewType) {
  const btnAnnual = document.getElementById('btnAnnual');
  const btnQuarterly = document.getElementById('btnQuarterly');
  const title = document.getElementById('finChartTitle');

  if (viewType === 'annual') {
    btnAnnual.classList.add('active');
    btnQuarterly.classList.remove('active');
    title.textContent = 'FINANCIAL PERFORMANCE (10 YEARS)';
    if (window.currentFinData && window.currentFinData.annual) {
      renderFinancialCharts(window.currentFinData.annual, false);
    }
  } else {
    btnQuarterly.classList.add('active');
    btnAnnual.classList.remove('active');
    title.textContent = 'FINANCIAL PERFORMANCE (QUARTERLY)';
    if (window.currentFinData && window.currentFinData.quarterly) {
      renderFinancialCharts(window.currentFinData.quarterly, true);
    }
  }
}

let finChartLeftInstance = null;
let finChartRightInstance = null;
let finChartCFOInstance = null;
let finChartDEInstance = null;
let finChartDPSInstance = null;

function renderFinancialCharts(history, isQuarterly = false) {
  const labels = history.map(h => isQuarterly ? h.quarter : h.year);
  const revenue = history.map(h => h.revenue);
  const netIncome = history.map(h => h.net_income);
  const npm = history.map(h => h.npm);
  const eps = history.map(h => h.eps);
  const cfo = history.map(h => h.cfo);
  const deRatio = history.map(h => h.de_ratio);
  const dps = history.map(h => h.dps);

  const leftCtx = document.getElementById('finChartLeft').getContext('2d');
  const rightCtx = document.getElementById('finChartRight').getContext('2d');
  const cfoCtx = document.getElementById('finChartCFO').getContext('2d');
  const deCtx = document.getElementById('finChartDE').getContext('2d');
  const dpsCtx = document.getElementById('finChartDPS').getContext('2d');

  if (finChartLeftInstance) finChartLeftInstance.destroy();
  if (finChartRightInstance) finChartRightInstance.destroy();
  if (finChartCFOInstance) finChartCFOInstance.destroy();
  if (finChartDEInstance) finChartDEInstance.destroy();
  if (finChartDPSInstance) finChartDPSInstance.destroy();

  const chartFont = { family: 'Inter', size: 10 };
  const legendCfg = { position: 'top', align: 'end', labels: { color: '#a0aec0', font: { family: 'Inter', size: 10, weight: '600' }, boxWidth: 10 } };
  const xScale = { ticks: { color: '#718096', font: chartFont }, grid: { display: false } };
  const gridLine = { color: 'rgba(255,255,255,0.05)' };

  finChartLeftInstance = new Chart(leftCtx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Revenue',
          data: revenue,
          backgroundColor: '#3182ce',
          order: 2,
          yAxisID: 'y'
        },
        {
          label: 'Net Profit',
          data: netIncome,
          backgroundColor: '#ed8936',
          order: 3,
          yAxisID: 'y'
        },
        {
          label: 'NPM (%)',
          data: npm,
          borderColor: '#f6e05e',
          borderWidth: 2,
          pointBackgroundColor: '#f6e05e',
          type: 'line',
          order: 1,
          yAxisID: 'y1',
          tension: 0.1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: legendCfg },
      scales: {
        x: xScale,
        y: { 
          ticks: { color: '#718096', font: chartFont, callback: function(value) { return value.toLocaleString(); } },
          grid: gridLine,
          title: { display: true, text: 'Million THB', color: '#718096', font: { family: 'Inter', size: 9, weight: '600' } }
        },
        y1: {
          position: 'right',
          ticks: { color: '#f6e05e', font: chartFont },
          grid: { display: false },
          title: { display: true, text: 'Margin %', color: '#f6e05e', font: { family: 'Inter', size: 9, weight: '600' } }
        }
      }
    }
  });

  finChartRightInstance = new Chart(rightCtx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'EPS (THB)',
        data: eps,
        backgroundColor: '#48bb78',
        borderRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: legendCfg },
      scales: {
        x: xScale,
        y: { 
          ticks: { color: '#718096', font: chartFont, callback: function(value) { return value.toLocaleString(); } },
          grid: gridLine,
          title: { display: true, text: 'THB / Share', color: '#718096', font: { family: 'Inter', size: 9, weight: '600' } }
        }
      }
    }
  });

  // ── CFO Chart (Bar - Teal) ──
  finChartCFOInstance = new Chart(cfoCtx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'CFO (M THB)',
        data: cfo,
        backgroundColor: cfo.map(v => v != null && v >= 0 ? '#38b2ac' : '#fc8181'),
        borderRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: legendCfg },
      scales: {
        x: xScale,
        y: {
          ticks: { color: '#718096', font: chartFont, callback: function(value) { return value.toLocaleString(); } },
          grid: gridLine,
          title: { display: true, text: 'Million THB', color: '#718096', font: { family: 'Inter', size: 9, weight: '600' } }
        }
      }
    }
  });

  // ── D/E Ratio Chart (Line - Gold) ──
  finChartDEInstance = new Chart(deCtx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'D/E Ratio',
        data: deRatio,
        borderColor: '#d69e2e',
        borderWidth: 2,
        pointBackgroundColor: '#d69e2e',
        pointRadius: 4,
        fill: true,
        backgroundColor: 'rgba(214,158,46,0.08)',
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: legendCfg },
      scales: {
        x: xScale,
        y: {
          ticks: { color: '#718096', font: chartFont },
          grid: gridLine,
          title: { display: true, text: 'Ratio', color: '#718096', font: { family: 'Inter', size: 9, weight: '600' } }
        }
      }
    }
  });

  // ── DPS Chart (Bar - Purple) ──
  finChartDPSInstance = new Chart(dpsCtx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'DPS (THB)',
        data: dps,
        backgroundColor: '#b794f4',
        borderRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: legendCfg },
      scales: {
        x: xScale,
        y: {
          ticks: { color: '#718096', font: chartFont, callback: function(value) { return value.toLocaleString(); } },
          grid: gridLine,
          title: { display: true, text: 'THB / Share', color: '#718096', font: { family: 'Inter', size: 9, weight: '600' } }
        }
      }
    }
  });
}

// ============================================================ Helpers
function set(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }

function setFV(valId, mosId, fv, mos) {
  const valEl = document.getElementById(valId);
  const mosEl = document.getElementById(mosId);
  if (valEl) valEl.textContent = fv != null ? (+fv).toFixed(2) : 'N/A';
  if (mosEl) {
    if (mos == null) { mosEl.textContent = '—'; mosEl.className = 'mos-badge'; }
    else { mosEl.textContent = (mos >= 0 ? '+' : '') + (+mos).toFixed(1) + '%'; mosEl.className = 'mos-badge ' + (mos >= 0 ? 'pos' : 'neg'); }
  }
}

function setMetric(tileId, valId, rawVal, colorKey, displayStr) {
  const valEl = document.getElementById(valId);
  if (valEl) valEl.textContent = displayStr || '—';
}

function applyColorMap(colors) {
  const map = { 'npm':'m-gpm','de':'m-de','sale_growth':'m-saleg','eps_growth':'m-epsg',
    'pe':'m-pe','peg':'m-peg','pbv':'m-pbv','ps':'m-ps','mktcap_rev':'m-mktrev','rotc':'m-rotc','roic':'m-roic' };
  document.querySelectorAll('.metric-tile').forEach(el => el.classList.remove('green','yellow','red'));
  Object.entries(colors).forEach(([key, color]) => {
    const tileId = map[key]; if (!tileId) return;
    const tile = document.getElementById(tileId);
    if (tile && color && color !== 'gray') tile.classList.add(color);
  });
}

// ============================================================ Momentum
async function fetchMomentum(symbol) {
  try {
    const resp = await fetch('/api/momentum', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ symbol })
    });
    const data = await resp.json();
    if (data.error) return;
    renderMomentum(data);
  } catch(e) { console.warn('Momentum fetch failed:', e); }
}

function renderMomentum(d) {
  // Signal cards
  const sigVol = document.getElementById('sig-volume');
  const sigGap = document.getElementById('sig-gap');
  const sigMom = document.getElementById('sig-momentum');

  // Volume spike
  set('sig-vol-ratio', d.volume_ratio_5d + 'x');
  set('sig-vol-detail', `Today (${d.today_date||''}): ${fmtVol(d.today_volume)} vs 5D Avg: ${fmtVol(d.avg_5d_volume)}`);
  sigVol.className = 'signal-card ' + (d.volume_spike ? 'bullish active-pulse' : 'neutral');

  // Gap
  const gapSign = d.price_gap_pct >= 0 ? '+' : '';
  set('sig-gap-value', gapSign + d.price_gap_pct.toFixed(2) + '%');
  set('sig-gap-detail', `Open ${d.today_date||''}: ${fmt(d.today_open)} vs Close ${d.yesterday_date||''}: ${fmt(d.yesterday_close)}`);
  sigGap.className = 'signal-card ' + (d.gap_up ? 'bullish' : d.gap_down ? 'bearish' : 'neutral');

  // Momentum signal
  set('sig-mom-signal', d.momentum_signal);
  const isBull = ['STRONG BUY','BUY','BULLISH'].includes(d.momentum_signal);
  const isBear = ['STRONG SELL','SELL','BEARISH'].includes(d.momentum_signal);
  set('sig-mom-detail', `${d.today_date||''} | Change: ${d.price_change >= 0 ? '+' : ''}${d.price_change_pct.toFixed(2)}%`);
  sigMom.className = 'signal-card ' + (isBull ? 'bullish active-pulse' : isBear ? 'bearish' : 'neutral');

  // Summary stats
  set('mom-today-vol', fmtVol(d.today_volume));
  set('mom-5d-vol', fmtVol(d.avg_5d_volume));
  set('mom-20d-vol', fmtVol(d.avg_20d_volume));
  set('mom-price-chg', (d.price_change >= 0 ? '+' : '') + d.price_change_pct.toFixed(2) + '%');
  set('mom-consec-up', d.consec_up + ' days');
  set('mom-consec-dn', d.consec_down + ' days');

  // Institute vs Retail bar
  document.getElementById('irb-inst').style.width = d.est_institute_pct + '%';
  document.getElementById('irb-retail').style.width = d.est_retail_pct + '%';
  set('irb-inst-pct', d.est_institute_pct);
  set('irb-retail-pct', d.est_retail_pct);

  // OHLCV table
  const tbody = document.getElementById('momentumBody');
  tbody.innerHTML = d.daily.slice().reverse().map(r => {
    const cls = r.change_pct >= 0 ? 'vol-up' : 'vol-down';
    return `<tr>
      <td>${r.date}</td><td>${fmt(r.open)}</td><td>${fmt(r.high)}</td>
      <td>${fmt(r.low)}</td><td>${fmt(r.close)}</td>
      <td>${fmtVol(r.volume)}</td>
      <td class="${cls}">${r.change_pct >= 0 ? '+' : ''}${r.change_pct.toFixed(2)}%</td>
    </tr>`;
  }).join('');

  // Volume chart
  drawVolumeChart(d.daily, d.avg_5d_volume);
}

function drawVolumeChart(daily, avg5d) {
  const canvas = document.getElementById('volumeChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  
  // Fallback to 900x200 if tab is hidden (display:none)
  const W = canvas.clientWidth || 900;
  const H = canvas.clientHeight || 200;
  
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  if (!daily || daily.length === 0) return;
  const maxVol = Math.max(...daily.map(d => d.volume), avg5d) * 1.1;
  const barW = Math.max(4, (W - 40) / daily.length - 2);
  const pad = { left: 10, bottom: 25, top: 10 };
  const chartH = H - pad.bottom - pad.top;

  daily.forEach((d, i) => {
    const x = pad.left + i * ((W - pad.left - 10) / daily.length);
    const h = (d.volume / maxVol) * chartH;
    const y = pad.top + chartH - h;
    ctx.fillStyle = d.change_pct >= 0 ? 'rgba(72,187,120,0.7)' : 'rgba(252,129,129,0.7)';
    ctx.fillRect(x, y, barW, h);
  });

  // Avg 5D line
  const avgY = pad.top + chartH - (avg5d / maxVol) * chartH;
  ctx.strokeStyle = 'rgba(246,216,96,0.8)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([5, 3]);
  ctx.beginPath(); ctx.moveTo(pad.left, avgY); ctx.lineTo(W - 10, avgY); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(246,216,96,0.9)';
  ctx.font = 'bold 11px Inter';
  ctx.fillText('5D Avg', W - 55, avgY - 6);

  // X-axis labels (every 5th)
  ctx.fillStyle = '#a0aec0';
  ctx.font = '600 10px Inter';
  daily.forEach((d, i) => {
    if (i % 5 === 0 || i === daily.length - 1) {
      const x = pad.left + i * ((W - pad.left - 10) / daily.length);
      ctx.fillText(d.date.slice(5), x, H - 5);
    }
  });
}

// ============================================================ News
async function fetchNews(symbol) {
  const feed = document.getElementById('newsFeed');
  feed.innerHTML = Array(4).fill('<div class="news-skeleton"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div></div>').join('');

  try {
    const resp = await fetch('/api/news', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ symbol, days: 30 })
    });
    const data = await resp.json();
    currentNews = data.articles || [];
    buildNewsFilters(data.sources || []);
    renderNews(currentNews);
    set('newsCount', currentNews.length + ' articles');
  } catch(e) {
    feed.innerHTML = '<div class="news-empty">Failed to fetch news.</div>';
  }
}

function buildNewsFilters(sources) {
  const container = document.getElementById('newsFilters');
  container.innerHTML = '<button class="news-filter-btn active" data-source="all">ALL</button>';
  sources.forEach(src => {
    const btn = document.createElement('button');
    btn.className = 'news-filter-btn';
    btn.dataset.source = src;
    btn.textContent = src.split(' (')[0].toUpperCase();
    container.appendChild(btn);
  });
  container.querySelectorAll('.news-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.news-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentNewsFilter = btn.dataset.source;
      const filtered = currentNewsFilter === 'all' ? currentNews
        : currentNews.filter(a => a.source && a.source.includes(currentNewsFilter));
      renderNews(filtered);
    });
  });
}

function renderNews(articles) {
  const feed = document.getElementById('newsFeed');
  if (!articles || articles.length === 0) {
    feed.innerHTML = '<div class="news-empty">No news found for this stock in the last 30 days.</div>';
    return;
  }
  feed.innerHTML = articles.map(a => {
    const badgeClass = getBadgeClass(a.source || '');
    const dateStr = a.date ? getRelativeDate(a.date) : '';
    const url = a.url || '#';
    return `<div class="news-card">
      <div class="news-card-header">
        <span class="news-source-badge ${badgeClass}">${a.source_icon || '📰'} ${a.source || 'Unknown'}</span>
        <span class="news-date">${dateStr}</span>
      </div>
      <a href="${url}" target="_blank" rel="noopener noreferrer" class="news-title">${a.title || '—'}</a>
      ${a.snippet && a.snippet !== a.title ? `<div class="news-snippet">${a.snippet}</div>` : ''}
    </div>`;
  }).join('');
}

function getBadgeClass(source) {
  const s = source.toLowerCase();
  if (s.includes('set')) return 'set';
  if (s.includes('yahoo')) return 'yahoo';
  if (s.includes('thunhoon')) return 'thunhoon';
  if (s.includes('gapfocus')) return 'gapfocus';
  if (s.includes('google')) return 'google';
  if (s.includes('ryt9')) return 'ryt9';
  return 'default';
}

function getRelativeDate(dateStr) {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - d) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Yesterday';
    if (diff < 7) return diff + ' days ago';
    return dateStr;
  } catch(e) { return dateStr; }
}

// ============================================================ Short List
async function addToShortList() {
  if (!currentResult) { alert('Please run a valuation first.'); return; }
  const resp = await fetch('/api/shortlist/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(currentResult)
  });
  const data = await resp.json();
  renderShortList(data.items);
  setStatus(`✅ ${currentResult.symbol} added to Short List (${data.count} total)`, 'success');
  document.querySelector('[data-tab="shortlist"]').click();
}

async function deleteFromShortList(idx) {
  const resp = await fetch('/api/shortlist/delete', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ index: idx })
  });
  const data = await resp.json();
  renderShortList(data.items);
}

async function clearShortList() {
  if (!confirm('Clear the entire short list?')) return;
  await fetch('/api/shortlist/clear', { method: 'POST' });
  renderShortList([]);
}

function renderShortList(items) {
  const tbody = document.getElementById('shortlistBody');
  if (!items || items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="17" class="empty-msg">No stocks added yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((r, i) => {
    const fc = r.forecast || {};
    return `<tr>
      <td>${i+1}</td><td>${r.symbol||'—'}</td><td>${fmt(r.price)}</td>
      <td>${fmt(r.fv_dcf)}</td><td>${fmt(r.fv_div)}</td><td>${fmt(r.fv_ddm)}</td>
      <td>${fmt(r.fv_per)}</td><td>${fmt(r.fv_pbv)}</td>
      <td>${r.mos_dcf!=null?(r.mos_dcf>=0?'+':'')+fmt(r.mos_dcf)+'%':'—'}</td>
      <td>${fmt(r.pe)}</td><td>${fmtP(r.roe)}</td><td>${fmt(r.de)}</td>
      <td>${fmtP(fc.yoy_eps_growth)}</td><td>${fmtP(r.sale_growth)}</td>
      <td>${fmtP(fc.forecast_yield)}</td><td>${r.timestamp||'—'}</td>
      <td><button class="btn-delete" onclick="deleteFromShortList(${i})">✕</button></td>
    </tr>`;
  }).join('');
}

// Load shortlist on page load
(async () => {
  try {
    const resp = await fetch('/api/shortlist');
    const data = await resp.json();
    if (data.items && data.items.length > 0) renderShortList(data.items);
  } catch(e) {}
})();

// ============================================================ UI helpers
function clearResult() {
  currentResult = null;
  const ids = ['val-company','val-price','val-hi','val-lo','fv-dcf','fv-div','fv-ddm','fv-per','fv-pbv',
    'sens-min','sens-max','mv-pe','mv-pbv','mv-peg','mv-ebitda','mv-eps','mv-de','mv-fyield',
    'mv-ev','mv-eveb','mv-roa','mv-dps','mv-payout','mv-gpm','mv-ebit','mv-epsg','mv-saleg',
    'mv-ps','mv-rotc','mv-roic','mv-mktrev','dp-npm','dp-at','dp-fl','dp-roe',
    'highlightBox','dividendPolicyBox','ft-eps','ft-price','ft-mos','ft-dps','ft-yield','ft-epsG',
    'companyNameShort','companyFull','companySector','sectorDisplay','waccDisplay','sharesDisplay','mktCapDisplay','assume-growth'];
  ids.forEach(id => set(id, '—'));
  ['mos-dcf','mos-div','mos-ddm','mos-per','mos-pbv'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = '—'; el.className = 'mos-badge'; }
  });
  document.querySelectorAll('.metric-tile').forEach(el => el.classList.remove('green','yellow','red'));
  const cLink = document.getElementById('consensusLink');
  if (cLink) cLink.style.display = 'none';
  setStatus('Cleared. Enter a symbol and click SUBMIT.', '');
}

function setStatus(msg, type) {
  const el = document.getElementById('status-box');
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-box ' + (type || '');
}

function showLoading(visible) {
  const el = document.getElementById('loadingOverlay');
  if (el) el.classList.toggle('hidden', !visible);
}

// ============================================================ Technical Chart Tab (Valuation)
let valTechChart = null;

async function fetchAndRenderValTechChart(symbol) {
  document.getElementById('techTabSymbolDisplay').textContent = symbol;
  const canvas = document.getElementById('valTechChartCanvas');
  
  if (!window.LightweightCharts) {
    canvas.innerHTML = '<div style="color:var(--red)">LightweightCharts library not loaded.</div>';
    return;
  }

  try {
    const res = await fetch('/api/historical_chart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, period: '5y' })
    });
    const result = await res.json();
    if (result.error) throw new Error(result.error);

    // Give UI a moment
    setTimeout(() => {
      // Cleanup old chart
      if (valTechChart) {
        valTechChart.remove();
        valTechChart = null;
      }
      canvas.innerHTML = '';

      const data = result.data;
      const chartOptions = {
        width: canvas.clientWidth || 800,
        height: canvas.clientHeight || 600,
        layout: { background: { color: '#000000' }, textColor: '#d1d4dc' },
        grid: { vertLines: { color: 'rgba(42, 46, 57, 0.3)' }, horzLines: { color: 'rgba(42, 46, 57, 0.3)' } },
        rightPriceScale: { borderColor: 'rgba(197, 203, 206, 0.4)' },
        timeScale: { borderColor: 'rgba(197, 203, 206, 0.4)', timeVisible: true },
        crosshair: { mode: LightweightCharts.CrosshairMode ? LightweightCharts.CrosshairMode.Normal : 0 }
      };

      valTechChart = LightweightCharts.createChart(canvas, chartOptions);

      const candleSeries = valTechChart.addCandlestickSeries({
        upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
        wickUpColor: '#26a69a', wickDownColor: '#ef5350',
      });
      candleSeries.setData(data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));

      const volSeries = valTechChart.addHistogramSeries({
        color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: ''
      });
      volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      volSeries.setData(data.map(d => ({
        time: d.time, value: d.volume, color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
      })));

      const ema50 = valTechChart.addLineSeries({ color: '#6366f1', lineWidth: 2, title: 'EMA 50' });
      ema50.setData(data.filter(d => d.ema50).map(d => ({ time: d.time, value: d.ema50 })));

      const ema200 = valTechChart.addLineSeries({ color: '#eab308', lineWidth: 2, title: 'EMA 200' });
      ema200.setData(data.filter(d => d.ema200).map(d => ({ time: d.time, value: d.ema200 })));

      valTechChart.timeScale().fitContent();
      
      // Resize observer to keep chart responsive
      if (!window.techChartObserver) {
        window.techChartObserver = new ResizeObserver(entries => {
          if (entries.length === 0 || entries[0].target !== canvas) return;
          const newRect = entries[0].contentRect;
          if (valTechChart && newRect.width > 0 && newRect.height > 0) {
            valTechChart.applyOptions({ height: newRect.height, width: newRect.width });
          }
        });
        window.techChartObserver.observe(canvas);
      }
    }, 50);

  } catch (err) {
    console.error(err);
    canvas.innerHTML = `<div style="padding: 20px; color:var(--red)">Failed to load chart: ${err.message}</div>`;
  }
}
