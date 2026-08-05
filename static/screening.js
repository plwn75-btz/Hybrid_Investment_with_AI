/* ═══════════════════════════════════════════════════════════════════
   SET Screening Dashboard — Client-side JavaScript
   Handles: form submit, SSE progress, dynamic table rendering,
            tab switching, sorting, CSV export
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── DOM refs ──────────────────────────────────────────────────────
    const form = document.getElementById('screeningForm');
    const btnRun = document.getElementById('btnRun');
    const btnText = btnRun.querySelector('.btn-text');
    const dateInput = document.getElementById('dateInput');
    const rsiSlider = document.getElementById('rsiSlider');
    const rsiInput = document.getElementById('rsiInput');
    const stochSlider = document.getElementById('stochSlider');
    const stochInput = document.getElementById('stochInput');
    const dateHint = document.getElementById('dateHint');

    const progressSection = document.getElementById('progressSection');
    const progressBar = document.getElementById('progressBar');
    const progressPct = document.getElementById('progressPct');
    const progressLabel = document.getElementById('progressLabel');
    const progressDetail = document.getElementById('progressDetail');

    const statusBadge = document.getElementById('statusBadge');
    const emptyState = document.getElementById('emptyState');
    const resultsContent = document.getElementById('resultsContent');
    const summaryCards = document.getElementById('summaryCards');
    const summaryDate = document.getElementById('summaryDate');
    const summaryStats = document.getElementById('summaryStats');
    const tabsContainer = document.getElementById('screenTabs');
    const tableWrap = document.getElementById('screenTableWrap');
    const chartDrawer = document.getElementById('screenChartDrawer');
    const chartCanvas = document.getElementById('screenChartCanvas');
    const chartSymbolDisplay = document.getElementById('chartSymbolDisplay');

    // ── State ─────────────────────────────────────────────────────────
    let screeningData = null;  // full results JSON
    let activeTab = '6';   // default to 6-criteria tab
    let sortCol = null;
    let sortAsc = true;
    let lwChart = null;
    let candlestickSeries = null;
    let volumeSeries = null;
    let ema50Series = null;
    let ema200Series = null;

    // ── Slider ↔ Input sync ───────────────────────────────────────────
    rsiSlider.addEventListener('input', () => { rsiInput.value = rsiSlider.value; });
    rsiInput.addEventListener('input', () => { rsiSlider.value = rsiInput.value; });
    stochSlider.addEventListener('input', () => { stochInput.value = stochSlider.value; });
    stochInput.addEventListener('input', () => { stochSlider.value = stochInput.value; });

    // ── Form submit ───────────────────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (btnRun.disabled) return;

        const params = {
            date: dateInput.value,
            rsi: parseInt(rsiInput.value, 10),
            stoch: parseInt(stochInput.value, 10)
        };

        // UI → running state
        btnRun.disabled = true;
        btnText.textContent = 'Screening…';
        if (statusBadge) {
            statusBadge.textContent = 'Running';
            statusBadge.className = 'header-badge running';
        }
        progressSection.classList.remove('hidden');
        progressBar.style.width = '0%';
        progressPct.textContent = '0%';
        progressLabel.textContent = 'Starting analysis…';
        progressDetail.textContent = '';
        emptyState.classList.add('hidden');
        resultsContent.classList.add('hidden');

        try {
            // 1. Start screening
            const res = await fetch('/api/screen', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            const startData = await res.json();

            if (!res.ok) {
                alert(startData.error || 'Failed to start screening');
                resetUI();
                return;
            }

            dateHint.textContent = startData.date_message || '';

            // 2. Listen to SSE progress
            await listenProgress();

            // 3. Fetch results
            const resResults = await fetch('/api/results');
            screeningData = await resResults.json();

            if (screeningData.error) {
                alert('Screening error: ' + screeningData.error);
                resetUI();
                return;
            }

            renderResults();

        } catch (err) {
            console.error(err);
            alert('Network error: ' + err.message);
        } finally {
            resetUI();
        }
    });

    // ── Polling progress listener ────────────────────────────────────
    async function listenProgress() {
        return new Promise((resolve) => {
            const interval = setInterval(async () => {
                try {
                    const res = await fetch('/api/progress');
                    const d = await res.json();
                    
                    const pct = d.pct || 0;
                    progressBar.style.width = pct + '%';
                    progressPct.textContent = pct + '%';
                    progressLabel.textContent = d.done ? 'Analysis complete!' : 'Analyzing stocks…';
                    progressDetail.textContent = `${d.current} / ${d.total} stocks`;

                    if (d.done) {
                        clearInterval(interval);
                        resolve();
                    }
                } catch (err) {
                    console.error('Progress poll failed:', err);
                }
            }, 1000);
        });
    }

    // ── Reset button ─────────────────────────────────────────────────
    function resetUI() {
        btnRun.disabled = false;
        btnText.textContent = 'Run Screening';
        if (statusBadge) {
            statusBadge.textContent = screeningData ? 'Done' : 'Ready';
            statusBadge.className = 'header-badge' + (screeningData ? ' done' : '');
        }
    }

    // ── Render all results ───────────────────────────────────────────
    function renderResults() {
        if (!screeningData || !screeningData.summary) return;

        const s = screeningData.summary;
        summaryDate.innerHTML = '📅 <strong>' + s.date + '</strong>';
        summaryStats.innerHTML = '✅ ' + s.total_processed + ' processed &nbsp;·&nbsp; ⏭️ ' + s.total_skipped + ' skipped &nbsp;·&nbsp; RSI&lt;' + s.rsi_threshold + ' &nbsp;·&nbsp; Stoch&gt;' + s.stoch_threshold;

        // Build summary cards (6 → 0)
        summaryCards.innerHTML = '';
        for (let i = 6; i >= 0; i--) {
            const cnt = s.counts[String(i)] || 0;
            const card = document.createElement('div');
            card.className = 'summary-card' + (String(i) === activeTab ? ' active' : '');
            card.dataset.criteria = i;
            card.innerHTML = `<div class="count">${cnt}</div><div class="label">${i} Criteria</div>`;
            card.addEventListener('click', () => switchTab(String(i)));
            summaryCards.appendChild(card);
        }

        // Build tabs (6 → 0)
        tabsContainer.innerHTML = '';
        for (let i = 6; i >= 0; i--) {
            const cnt = s.counts[String(i)] || 0;
            const btn = document.createElement('button');
            btn.className = 'tab-btn' + (String(i) === activeTab ? ' active' : '');
            btn.dataset.tab = i;
            btn.textContent = `${i} Criteria (${cnt})`;
            btn.addEventListener('click', () => switchTab(String(i)));
            tabsContainer.appendChild(btn);
        }

        renderTable(activeTab);

        emptyState.classList.add('hidden');
        resultsContent.classList.remove('hidden');
        resultsContent.classList.add('fade-in');
    }

    // ── Switch tab ───────────────────────────────────────────────────
    function switchTab(tabKey) {
        activeTab = tabKey;
        sortCol = null;
        sortAsc = true;

        // Update active states
        document.querySelectorAll('.summary-card').forEach(c => {
            c.classList.toggle('active', c.dataset.criteria === tabKey);
        });
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.tab === tabKey);
        });

        renderTable(tabKey);
    }

    // ── Render data table ────────────────────────────────────────────
    const COLUMNS = [
        { key: 'symbol', label: 'Symbol', type: 'string' },
        { key: 'close', label: 'Close', type: 'number' },
        { key: 'volume', label: 'Volume', type: 'number' },
        { key: 'volume_5d_avg', label: '5D Avg Vol', type: 'number' },
        { key: 'ema50', label: 'EMA50', type: 'number' },
        { key: 'ema200', label: 'EMA200', type: 'number' },
        { key: 'rsi', label: 'RSI', type: 'number' },
        { key: 'macd', label: 'MACD', type: 'number' },
        { key: 'stoch', label: 'Stoch', type: 'number' },
        { key: 'sar', label: 'SAR', type: 'number' },
        { key: 'bbl', label: 'BBL', type: 'number' },
        { key: 'bbm', label: 'BBM', type: 'number' },
        { key: 'bbu', label: 'BBU', type: 'number' },
        { key: 'c1', label: 'C1', type: 'bool' },
        { key: 'c2', label: 'C2', type: 'bool' },
        { key: 'c3', label: 'C3', type: 'bool' },
        { key: 'c4', label: 'C4', type: 'bool' },
        { key: 'c5', label: 'C5', type: 'bool' },
        { key: 'c6', label: 'C6', type: 'bool' },
    ];

    function renderTable(tabKey) {
        let rows = screeningData.results[tabKey] || [];

        // Sort
        if (sortCol !== null) {
            const col = COLUMNS[sortCol];
            rows = [...rows].sort((a, b) => {
                let va = a[col.key], vb = b[col.key];
                if (col.type === 'string') {
                    va = (va || '').toLowerCase();
                    vb = (vb || '').toLowerCase();
                    return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
                }
                if (col.type === 'bool') {
                    va = va ? 1 : 0;
                    vb = vb ? 1 : 0;
                }
                return sortAsc ? va - vb : vb - va;
            });
        }

        let html = '';

        // Export button
        html += '<div class="table-actions">';
        html += `<button class="btn-export" onclick="exportCSV('${tabKey}')">📥 Export CSV</button>`;
        html += '</div>';

        html += '<table class="data-table"><thead><tr>';
        COLUMNS.forEach((col, idx) => {
            const isSorted = sortCol === idx;
            const arrow = isSorted ? (sortAsc ? '▲' : '▼') : '⇅';
            html += `<th class="${isSorted ? 'sorted' : ''}" onclick="sortTable(${idx})">${col.label} <span class="sort-arrow">${arrow}</span></th>`;
        });
        html += '</tr></thead><tbody>';

        if (rows.length === 0) {
            html += `<tr class="no-data-row"><td colspan="${COLUMNS.length}">No stocks found matching ${tabKey} criteria</td></tr>`;
        } else {
            rows.forEach(row => {
                html += `<tr onclick="openStockChart('${row.symbol}', this)">`;
                COLUMNS.forEach(col => {
                    if (col.type === 'bool') {
                        const pass = row[col.key];
                        html += `<td><span class="criteria-badge ${pass ? 'pass' : 'fail'}">${pass ? '✓' : '✗'}</span></td>`;
                    } else if (col.key === 'symbol') {
                        html += `<td class="symbol">${row[col.key]}</td>`;
                    } else {
                        const v = row[col.key];
                        if (typeof v === 'number') {
                            if (col.key === 'volume' || col.key === 'volume_5d_avg') {
                                html += `<td>${v.toLocaleString()}</td>`;
                            } else {
                                html += `<td>${v.toFixed(col.key === 'close' ? 2 : 4)}</td>`;
                            }
                        } else {
                            html += `<td>${v}</td>`;
                        }
                    }
                });
                html += '</tr>';
            });
        }

        html += '</tbody></table>';
        tableWrap.innerHTML = html;
    }

    // ── Sort handler (global) ────────────────────────────────────────
    window.sortTable = function (colIdx) {
        if (sortCol === colIdx) {
            sortAsc = !sortAsc;
        } else {
            sortCol = colIdx;
            sortAsc = true;
        }
        renderTable(activeTab);
    };

    // ── CSV export (global) ──────────────────────────────────────────
    window.exportCSV = function (tabKey) {
        const rows = screeningData.results[tabKey] || [];
        if (rows.length === 0) return;

        const headers = COLUMNS.map(c => c.label);
        const csvRows = [headers.join(',')];

        rows.forEach(row => {
            const vals = COLUMNS.map(col => {
                const v = row[col.key];
                if (col.type === 'bool') return v ? 'PASS' : 'FAIL';
                return v;
            });
            csvRows.push(vals.join(','));
        });

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `SET_Screening_${tabKey}_Criteria_${screeningData.summary.date}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    };

    // ── Technical Chart Logic ────────────────────────────────────────
    window.openStockChart = async function(symbol, rowEl) {
        // Highlight row
        document.querySelectorAll('table.data-table tbody tr').forEach(tr => tr.classList.remove('active-row'));
        if (rowEl) rowEl.classList.add('active-row');

        chartSymbolDisplay.textContent = symbol;
        chartDrawer.classList.remove('hidden');

        try {
            const res = await fetch('/api/historical_chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol, period: '5y' })
            });
            const result = await res.json();
            if (result.error) throw new Error(result.error);

            // Give the browser a moment to render the drawer before creating the chart
            setTimeout(() => {
                renderLightweightChart(result.data);
            }, 50);
        } catch (err) {
            console.error(err);
            chartCanvas.innerHTML = `<div style="padding:20px; color:var(--red)">Failed to load chart: ${err.message}</div>`;
        }
    };

    function renderLightweightChart(data) {
        // Cleanup previous
        if (lwChart) {
            try { lwChart.remove(); } catch(e) {}
            lwChart = null;
        }
        chartCanvas.innerHTML = '';

        if (!window.LightweightCharts) {
            chartCanvas.innerHTML = '<div style="padding:20px; color:var(--red)">LightweightCharts library not loaded.</div>';
            return;
        }

        const chartOptions = {
            width: chartCanvas.clientWidth || 800,
            height: chartCanvas.clientHeight || 340,
            layout: {
                background: { color: '#000000' },
                textColor: '#d1d4dc',
            },
            grid: {
                vertLines: { color: 'rgba(42, 46, 57, 0.3)' },
                horzLines: { color: 'rgba(42, 46, 57, 0.3)' },
            },
            rightPriceScale: {
                borderColor: 'rgba(197, 203, 206, 0.4)',
            },
            timeScale: {
                borderColor: 'rgba(197, 203, 206, 0.4)',
                timeVisible: true,
            },
            crosshair: {
                mode: (window.LightweightCharts && LightweightCharts.CrosshairMode) ? LightweightCharts.CrosshairMode.Normal : 0,
            },
        };

        try {
            lwChart = LightweightCharts.createChart(chartCanvas, chartOptions);

            // Add Candlestick series
            candlestickSeries = lwChart.addCandlestickSeries({
                upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
                wickUpColor: '#26a69a', wickDownColor: '#ef5350',
            });
            candlestickSeries.setData(data.map(d => ({
                time: d.time,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close
            })));

            // Add Volume series
            volumeSeries = lwChart.addHistogramSeries({
                color: '#26a69a',
                priceFormat: { type: 'volume' },
                priceScaleId: '', // overlay
            });
            volumeSeries.priceScale().applyOptions({
                scaleMargins: { top: 0.8, bottom: 0 },
            });
            volumeSeries.setData(data.map(d => ({
                time: d.time,
                value: d.volume,
                color: d.close >= d.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
            })));

            // Add EMA 50
            ema50Series = lwChart.addLineSeries({
                color: '#6366f1', // accent blue/purple
                lineWidth: 2,
                title: 'EMA 50',
            });
            ema50Series.setData(data.filter(d => d.ema50).map(d => ({
                time: d.time,
                value: d.ema50
            })));

            // Add EMA 200
            ema200Series = lwChart.addLineSeries({
                color: '#eab308', // yellow
                lineWidth: 2,
                title: 'EMA 200',
            });
            ema200Series.setData(data.filter(d => d.ema200).map(d => ({
                time: d.time,
                value: d.ema200
            })));

            lwChart.timeScale().fitContent();
        } catch (e) {
            console.error('Chart creation error:', e);
            chartCanvas.innerHTML = `<div style="padding:20px; color:var(--red)">Chart error: ${e.message}</div>`;
        }
    }

    window.closeScreenChart = function() {
        chartDrawer.classList.add('hidden');
        document.querySelectorAll('table.data-table tbody tr').forEach(tr => tr.classList.remove('active-row'));
        if (lwChart) {
            lwChart.remove();
            lwChart = null;
        }
    };

})();
