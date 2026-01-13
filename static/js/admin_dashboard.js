const ADMIN_DASHBOARD_DEBUG = false;

document.addEventListener('DOMContentLoaded', function () {
    initializeDashboard();
    addAnimationStyles();
    addInteractiveEffects();
    startLiveClock();
    attachSidebarHandlers();
    // API-first: load dashboard data from /admin/dashboard-data/ and render
    loadAndRenderDashboard();
});

// ------------------ API-driven helpers and UI glue ------------------
function showSpinner() {
    try {
        const el = document.getElementById('dashboard-loading');
        if (el) {
            el.style.display = 'flex';
            el.setAttribute('aria-hidden', 'false');
        }
    } catch (e) { /* ignore */ }
}
function hideSpinner() {
    try {
        const el = document.getElementById('dashboard-loading');
        if (el) {
            el.style.display = 'none';
            el.setAttribute('aria-hidden', 'true');
        }
    } catch (e) { /* ignore */ }
}
function showErrorBanner(msg) {
    try {
        const existing = document.getElementById('dashboard-error-banner');
        if (existing) existing.parentNode.removeChild(existing);
        const container = document.querySelector('.dashboard-container');
        if (!container) return;
        const div = document.createElement('div');
        div.id = 'dashboard-error-banner';
        div.className = 'alert alert-danger';
        div.role = 'alert';
        div.innerHTML = `<strong>Dashboard error:</strong> ${msg} <button class="btn btn-sm btn-outline-light ms-2" id="dismiss-dashboard-error">Dismiss</button>`;
        container.insertBefore(div, container.firstChild);
        document.getElementById('dismiss-dashboard-error').addEventListener('click', function(){ if (div.parentNode) div.parentNode.removeChild(div); });
    } catch (e) { console.warn('showErrorBanner error', e); }
}

function fetchDashboardData(options = {}) {
    const params = new URLSearchParams();
    const range = options.range || (window.DASHBOARD_SELECTED_RANGE || '30');
    const tx_type = options.tx_type || 'all';
    params.set('range', range);
    if (tx_type && tx_type !== 'all') params.set('tx_type', tx_type);
    const url = `/admin/dashboard-data/?${params.toString()}`;
    return fetch(url, { credentials: 'same-origin' }).then(r => {
        if (!r.ok) throw new Error('Network response was not ok');
        return r.json();
    });
}

function renderFromPayload(payload, options = {}) {
    try {
        // Update the hidden application/json blob used by legacy chart renderer
        const el = document.getElementById('chart-data');
        if (el) {
            el.textContent = JSON.stringify({
                dates: payload.chart_dates || [],
                totals: payload.chart_totals || [],
                pieLabels: payload.pie_labels || [],
                pieData: payload.pie_data || []
            });
        }
        // Update KPI cards
        updateKpisFromPayload(payload);
        // Update recent transactions and top users lists
        updateRecentLists(payload);
        // Announce kpi changes for screen readers
        const live = document.getElementById('kpi-live');
        if (live) {
            live.textContent = `Total Users ${payload.total_users}. Total Transactions ${payload.total_transactions}.`;
        }
        // Re-initialize charts (will read chart-data element)
        setTimeout(() => {
            try { initializeCharts(); } catch (e) { console.warn('renderFromPayload init charts failed', e); }
        }, 50);
    } catch (e) {
        console.warn('renderFromPayload error', e);
    }
}

function loadAndRenderDashboard(opts = {}) {
    showSpinner();
    const options = Object.assign({}, { range: window.DASHBOARD_SELECTED_RANGE || '30', tx_type: 'all' }, opts);
    fetchDashboardData(options).then(payload => {
        hideSpinner();
        renderFromPayload(payload, options);
        // update UI active states based on payload
        try {
            const selectedRange = payload.selected_range || options.range;
            document.querySelectorAll('.btn-range').forEach(b => {
                b.classList.toggle('active', b.getAttribute('data-range') === String(selectedRange));
            });
            const txType = payload.tx_type || options.tx_type || 'all';
            document.querySelectorAll('.btn-tx-type').forEach(b => {
                b.classList.toggle('active', b.getAttribute('data-tx') === String(txType));
            });
        } catch (e) { /* ignore */ }
        // push state to make URL shareable
        try {
            const newUrl = new URL(window.location.href);
            newUrl.searchParams.set('range', payload.selected_range || options.range);
            if (payload.tx_type && payload.tx_type !== 'all') newUrl.searchParams.set('tx_type', payload.tx_type); else newUrl.searchParams.delete('tx_type');
            window.history.replaceState({}, '', newUrl.toString());
        } catch (e) { /* ignore browsers without URL support */ }
    }).catch(err => {
        hideSpinner();
        showErrorBanner(err && err.message ? err.message : 'Failed to load dashboard data');
        console.error('loadAndRenderDashboard error', err);
    });
}

function attachSidebarHandlers() {
    // Range buttons
    document.querySelectorAll('.btn-range').forEach(btn => {
        btn.addEventListener('click', function(e){
            e.preventDefault();
            document.querySelectorAll('.btn-range').forEach(b=>b.classList.remove('active'));
            this.classList.add('active');
            const range = this.getAttribute('data-range');
            window.DASHBOARD_SELECTED_RANGE = range;
            loadAndRenderDashboard({range: range});
        });
    });
    // Tx type
    document.querySelectorAll('.btn-tx-type').forEach(btn => {
        btn.addEventListener('click', function(e){
            e.preventDefault();
            document.querySelectorAll('.btn-tx-type').forEach(b=>b.classList.remove('active'));
            this.classList.add('active');
            const tx = this.getAttribute('data-tx');
            loadAndRenderDashboard({tx_type: tx});
        });
    });
    // Chart toggles
    document.querySelectorAll('.btn-chart-toggle').forEach(cb => {
        cb.addEventListener('change', function(){
            const val = this.value;
            if (val === 'line') {
                const el = document.querySelector('#txChart')?.closest('.chart-container');
                if (el) el.style.display = this.checked ? 'block' : 'none';
            }
            if (val === 'pie') {
                const el = document.querySelector('#txPie')?.closest('.chart-container');
                if (el) el.style.display = this.checked ? 'block' : 'none';
            }
        });
    });
    // Refresh button
    const refresh = document.getElementById('refresh-dashboard');
    if (refresh) refresh.addEventListener('click', function(){ loadAndRenderDashboard(); });
}

function updateRecentLists(payload) {
    try {
        // Recent transactions table
        const tbody = document.querySelector('table.table tbody');
        if (tbody && Array.isArray(payload.recent_transactions)) {
            tbody.innerHTML = '';
            payload.recent_transactions.forEach(t => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${t.date} ${t.time}</td>
                    <td><code>${t.txid}</code></td>
                    <td>${t.user_email || ''}</td>
                    <td>${t.transaction_type === 'deposit' ? 'Deposit' : 'Withdrawal'}</td>
                    <td class="text-end">$${Number(t.amount).toFixed(2)}</td>
                `;
                tbody.appendChild(tr);
            });
            if (payload.recent_transactions.length === 0) {
                const tr = document.createElement('tr');
                tr.innerHTML = '<td colspan="5" class="text-center text-muted">No recent transactions</td>';
                tbody.appendChild(tr);
            }
        }
        // Top users list
        const topUsersList = document.querySelector('.card .list-unstyled');
        if (topUsersList && Array.isArray(payload.top_users)) {
            // naive replacement: find the Top Users card's list by anchor text
            const topUserEls = document.querySelectorAll('.card .list-unstyled');
            topUserEls.forEach(list => {
                // if list is in Top Users card (contains "Top Users" in the preceding header)
                const heading = list.closest('.card')?.querySelector('h6');
                if (heading && heading.textContent && heading.textContent.indexOf('Top Users') !== -1) {
                    list.innerHTML = '';
                    payload.top_users.forEach(u => {
                        const li = document.createElement('li');
                        li.className = 'py-2 border-bottom';
                        li.textContent = `${u.email} `;
                        const span = document.createElement('span');
                        span.className = 'float-end';
                        span.textContent = u.tx_count;
                        li.appendChild(span);
                        list.appendChild(li);
                    });
                    if (payload.top_users.length === 0) {
                        list.innerHTML = '<li class="py-3 text-muted">No activity yet</li>';
                    }
                }
            });
        }
    } catch (e) {
        console.warn('updateRecentLists error', e);
    }
}


function initializeDashboard() {
    // Simple fade-in for cards
    try {
        const cards = Array.from(document.querySelectorAll('.kpi-card, .chart-card, .action-card'));
        cards.forEach((card, index) => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(10px)';
            setTimeout(() => {
                card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, index * 80);
        });

        // Start KPI counter animations after reveal
        setTimeout(() => animateCounters(), 300);
    } catch (err) {
        document.querySelectorAll('.kpi-card, .chart-card, .action-card').forEach(card => {
            card.style.opacity = '1';
            card.style.transform = '';
        });
        console.error('initializeDashboard error:', err);
    }
}

function animateCounters() {
    const counters = document.querySelectorAll('.counter');
    counters.forEach(el => {
        const fmt = el.getAttribute('data-format') || 'number';
        
        // Get the current text and parse it
        let raw = el.textContent.trim();
        
        // Remove any formatting for parsing
        raw = raw.replace(/[^0-9.\-]/g, '');
        let target = parseFloat(raw);
        
        // If parsing fails, try to get from data attribute
        if (isNaN(target)) {
            const dataValue = el.getAttribute('data-value');
            if (dataValue) {
                target = parseFloat(dataValue) || 0;
            } else {
                target = 0;
            }
        }

        const isInt = Number.isInteger(target);
        const duration = 1500; // Increased duration for smoother animation
        const start = performance.now();
        const startVal = 0;

        function formatValue(v) {
            if (fmt === 'currency') {
                try {
                    return new Intl.NumberFormat('en-US', { 
                        style: 'currency', 
                        currency: 'USD', 
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2 
                    }).format(v);
                } catch (e) {
                    return '$' + v.toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,');
                }
            }
            if (isInt) {
                return Math.round(v).toLocaleString();
            }
            return v.toLocaleString(undefined, { 
                minimumFractionDigits: 2,
                maximumFractionDigits: 2 
            });
        }

        // Set initial value
        el.textContent = formatValue(startVal);

        function step(now) {
            const elapsed = Math.min((now - start) / duration, 1);
            // Easing function for smoother animation
            const eased = 1 - Math.pow(1 - elapsed, 3);
            const val = startVal + (target - startVal) * eased;
            
            el.textContent = formatValue(val);
            
            if (elapsed < 1) {
                requestAnimationFrame(step);
            } else {
                // Ensure final value is exact
                el.textContent = formatValue(target);
            }
        }

        requestAnimationFrame(step);
    });
}

function updateKpisFromPayload(payload) {
    try {
        document.querySelectorAll('.kpi-card').forEach(card => {
            const labelEl = card.querySelector('.small.text-muted');
            if (!labelEl) return;
            const label = labelEl.textContent.trim();
            const valueEl = card.querySelector('.kpi-value');
            if (!valueEl) return;
            if (label === 'Total Users' && typeof payload.total_users !== 'undefined') {
                valueEl.textContent = payload.total_users;
                valueEl.setAttribute('data-value', payload.total_users);
            }
            if (label === 'Total Transactions' && typeof payload.total_transactions !== 'undefined') {
                valueEl.textContent = payload.total_transactions;
                valueEl.setAttribute('data-value', payload.total_transactions);
            }
            if (label === 'Total Deposits' && typeof payload.total_deposits !== 'undefined') {
                // Format currency
                valueEl.textContent = Number(payload.total_deposits).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
                valueEl.setAttribute('data-value', payload.total_deposits);
            }
            if (label === 'Total Withdrawals' && typeof payload.total_withdrawals !== 'undefined') {
                valueEl.textContent = Number(payload.total_withdrawals).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
                valueEl.setAttribute('data-value', payload.total_withdrawals);
            }
        });

        // Update distribution stats (Deposits, Withdrawals)
        const statItems = Array.from(document.querySelectorAll('.distribution-stats .stat-item'));
        if (statItems.length >= 1 && typeof payload.total_deposits !== 'undefined') {
            const depEl = statItems[0].querySelector('.h5');
            if (depEl) depEl.textContent = '$' + Number(payload.total_deposits).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
        }
        if (statItems.length >= 2 && typeof payload.total_withdrawals !== 'undefined') {
            const wdEl = statItems[1].querySelector('.h5');
            if (wdEl) wdEl.textContent = '$' + Number(payload.total_withdrawals).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
        }
    } catch (e) {
        console.warn('updateKpisFromPayload error', e);
    }
    // re-run counter animations to reflect updated values
    try { animateCounters(); } catch(e) { /* ignore */ }
}

// Live date/time
function startLiveClock() {
    const dateEl = document.getElementById('live-date');
    const timeEl = document.getElementById('live-time');
    if (!dateEl || !timeEl) return;

    function update() {
        const now = new Date();
        const dateStr = now.toLocaleDateString(undefined, { 
            month: 'short', 
            day: '2-digit', 
            year: 'numeric' 
        });
        const timeStr = now.toLocaleTimeString(undefined, { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            hour12: false 
        });
        dateEl.textContent = dateStr;
        timeEl.textContent = timeStr;
    }

    update();
    setInterval(update, 1000);
}

function addAnimationStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .pulse-on-hover:hover { 
            transform: scale(1.02); 
            transition: transform 0.2s ease; 
        }
        .chart-loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
            color: #6c757d;
        }
        .chart-error {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
            color: #dc3545;
        }
    `;
    document.head.appendChild(style);
}

function initializeCharts() {
    if (!window.Chart) {
        console.error('Chart.js library not loaded');
        showChartFallback();
        return;
    }

    try {
        // Parse the consolidated JSON data
        const chartDataElement = document.getElementById('chart-data');
        if (!chartDataElement) {
            console.error('Chart data element not found');
            showChartFallback();
            return;
        }

        let chartData;
        const rawChartText = chartDataElement.textContent.trim();
        if (!rawChartText) {
            console.error('Chart data element is empty');
            showChartFallback();
            return;
        }
        try {
            chartData = JSON.parse(rawChartText);
            // Diagnostic: report parsed sizes and sample values
            const parsedInfo = {
                dates: Array.isArray(chartData.dates) ? chartData.dates.length : null,
                totals: Array.isArray(chartData.totals) ? chartData.totals.length : null,
                pieLabels: Array.isArray(chartData.pieLabels) ? chartData.pieLabels.length : null,
                pieData: Array.isArray(chartData.pieData) ? chartData.pieData.length : null,
                sampleDates: chartData.dates ? chartData.dates.slice(-3) : null,
                sampleTotals: chartData.totals ? chartData.totals.slice(-3) : null
            };
            console.info('chartData parsed', parsedInfo);
            updateDebugPanel({status: 'parsed', info: parsedInfo, raw: rawChartText.slice(0,1000)});

            // If server emitted empty arrays, fetch dynamic data via AJAX
            const emptyChart = (!Array.isArray(chartData.dates) || chartData.dates.length === 0) && (!Array.isArray(chartData.totals) || chartData.totals.length === 0);
            const emptyPie = (!Array.isArray(chartData.pieLabels) || chartData.pieLabels.length === 0) && (!Array.isArray(chartData.pieData) || chartData.pieData.length === 0);
            if (emptyChart && emptyPie) {
                const range = window.DASHBOARD_SELECTED_RANGE || '30';
                console.info('Embedded chart data empty — fetching /admin/dashboard-data/ ?range=' + range);
                fetch(`/admin/dashboard-data/?range=${encodeURIComponent(range)}`)
                    .then(r => r.json())
                    .then(payload => {
                        if (payload && Array.isArray(payload.chart_dates) && payload.chart_dates.length > 0) {
                            chartData = {
                                dates: payload.chart_dates,
                                totals: payload.chart_totals,
                                pieLabels: payload.pie_labels,
                                pieData: payload.pie_data
                            };
                            updateKpisFromPayload(payload);
                            updateDebugPanel({status: 'fetched', info: {dates: payload.chart_dates.length, totals: payload.chart_totals.length}});
                            // Re-run initialization now that chartData has valid values
                            // We simply call initializeCharts again after a short tick to avoid recursion issues
                            setTimeout(() => initializeCharts(), 50);
                            return;
                        } else {
                            updateDebugPanel({status: 'fetch_empty', info: payload});
                        }
                    }).catch(e => {
                        console.error('Failed to fetch dashboard data:', e);
                        updateDebugPanel({status: 'fetch_error', error: e && e.message});
                    });
            }

        } catch (e) {
            console.error('Failed to parse chart data. Raw content:', rawChartText, e);
            updateDebugPanel({status: 'parse_error', error: e && e.message, raw: rawChartText.slice(0,1000)});
            showChartFallback();
            return;
        }

        // Initialize Line Chart - Transactions
        const lineCtx = document.getElementById('txChart');
        if (lineCtx) {
            if (chartData.dates && chartData.totals && 
                chartData.dates.length > 0 && chartData.totals.length > 0) {
                
                // Add loading indicator
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'chart-loading';
                loadingDiv.innerHTML = '<i class="fas fa-spinner fa-spin fa-2x mb-2"></i><div>Loading chart...</div>';
                lineCtx.parentNode.appendChild(loadingDiv);

                setTimeout(() => {
                    try {
                        // Destroy any previous chart bound to this canvas
                        if (window.adminCharts && window.adminCharts.length) {
                            window.adminCharts = window.adminCharts.filter(c => {
                                try {
                                    if (c && c.canvas && c.canvas === lineCtx) {
                                        c.destroy();
                                        return false;
                                    }
                                } catch (e) { }
                                return true;
                            });
                        }
                        const chart = new Chart(lineCtx.getContext('2d'), {
                            type: 'line',
                            data: {
                                labels: chartData.dates,
                                datasets: [{
                                    label: 'Transaction Volume',
                                    data: chartData.totals,
                                    borderColor: 'rgba(26, 115, 232, 1)',
                                    backgroundColor: 'rgba(26, 115, 232, 0.1)',
                                    borderWidth: 3,
                                    tension: 0.4,
                                    fill: true,
                                    pointBackgroundColor: 'rgba(26, 115, 232, 1)',
                                    pointBorderColor: '#ffffff',
                                    pointBorderWidth: 2,
                                    pointRadius: 4,
                                    pointHoverRadius: 6
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: {
                                    legend: {
                                        display: false
                                    },
                                    tooltip: {
                                        mode: 'index',
                                        intersect: false,
                                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                                        titleFont: { size: 14 },
                                        bodyFont: { size: 13 },
                                        padding: 12,
                                        callbacks: {
                                            label: function(context) {
                                                return `$${context.parsed.y.toFixed(2)}`;
                                            }
                                        }
                                    }
                                },
                                scales: {
                                    x: {
                                        grid: {
                                            display: false
                                        },
                                        ticks: {
                                            font: {
                                                size: 11
                                            },
                                            maxRotation: 45
                                        }
                                    },
                                    y: {
                                        beginAtZero: true,
                                        grid: {
                                            color: 'rgba(0, 0, 0, 0.05)'
                                        },
                                        ticks: {
                                            font: {
                                                size: 11
                                            },
                                            callback: function(value) {
                                                return '$' + value.toLocaleString();
                                            }
                                        }
                                    }
                                },
                                interaction: {
                                    intersect: false,
                                    mode: 'nearest'
                                },
                                animation: {
                                    duration: 1000,
                                    easing: 'easeOutQuart'
                                }
                            }
                        });
                        
                        // Store reference to created chart for resize/cleanup
                        if (!window.adminCharts) window.adminCharts = [];
                        window.adminCharts.push(chart);

                        // Remove loading indicator
                        if (loadingDiv.parentNode) {
                            loadingDiv.parentNode.removeChild(loadingDiv);
                        }
                    } catch (e) {
                        console.error('Error creating line chart:', e);
                        showChartError(lineCtx.parentNode, 'Failed to load transaction chart');
                    }
                }, 100);
            } else {
                showChartError(lineCtx.parentNode, 'No transaction data available');
            }
        }

        // Initialize Pie Chart - Financial Distribution
        const pieCtx = document.getElementById('txPie');
        if (pieCtx) {
            if (chartData.pieLabels && chartData.pieData && 
                chartData.pieLabels.length > 0 && chartData.pieData.length > 0) {
                
                // Add loading indicator
                const loadingDiv = document.createElement('div');
                loadingDiv.className = 'chart-loading';
                loadingDiv.innerHTML = '<i class="fas fa-spinner fa-spin fa-2x mb-2"></i><div>Loading chart...</div>';
                pieCtx.parentNode.appendChild(loadingDiv);

                setTimeout(() => {
                    try {
                        // Destroy any previous chart bound to this canvas
                        if (window.adminCharts && window.adminCharts.length) {
                            window.adminCharts = window.adminCharts.filter(c => {
                                try {
                                    if (c && c.canvas && c.canvas === pieCtx) {
                                        c.destroy();
                                        return false;
                                    }
                                } catch (e) { }
                                return true;
                            });
                        }
                        const chart = new Chart(pieCtx.getContext('2d'), {
                            type: 'doughnut',
                            data: {
                                labels: chartData.pieLabels,
                                datasets: [{
                                    data: chartData.pieData,
                                    backgroundColor: [
                                        'rgba(40, 167, 69, 0.8)',    // Success green for Deposits
                                        'rgba(255, 193, 7, 0.8)',    // Warning yellow for Withdrawals
                                        'rgba(23, 162, 184, 0.8)'    // Info blue for Net Flow
                                    ],
                                    borderColor: [
                                        'rgba(40, 167, 69, 1)',
                                        'rgba(255, 193, 7, 1)',
                                        'rgba(23, 162, 184, 1)'
                                    ],
                                    borderWidth: 2,
                                    hoverOffset: 15
                                }]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                cutout: '65%',
                                plugins: {
                                    legend: {
                                        position: 'bottom',
                                        labels: {
                                            padding: 20,
                                            usePointStyle: true,
                                            pointStyle: 'circle',
                                            font: {
                                                size: 12
                                            }
                                        }
                                    },
                                    tooltip: {
                                        callbacks: {
                                            label: function(context) {
                                                const label = context.label || '';
                                                const value = context.parsed;
                                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                                const percentage = Math.round((value / total) * 100);
                                                return `${label}: $${value.toFixed(2)} (${percentage}%)`;
                                            }
                                        }
                                    }
                                },
                                animation: {
                                    animateScale: true,
                                    animateRotate: true,
                                    duration: 1200
                                }
                            }
                        });
                        
                        // Store reference to created chart for resize/cleanup
                        if (!window.adminCharts) window.adminCharts = [];
                        window.adminCharts.push(chart);

                        // Remove loading indicator
                        if (loadingDiv.parentNode) {
                            loadingDiv.parentNode.removeChild(loadingDiv);
                        }
                    } catch (e) {
                        console.error('Error creating pie chart:', e);
                        showChartError(pieCtx.parentNode, 'Failed to load distribution chart');
                    }
                }, 100);
            } else {
                showChartError(pieCtx.parentNode, 'No distribution data available');
            }
        }

    } catch (error) {
        console.error('Error initializing charts:', error);
        showChartFallback();
    }
}

function showChartError(container, message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'chart-error';
    errorDiv.innerHTML = `
        <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
        <div class="fw-bold">${message}</div>
        <small class="text-muted">Try refreshing the page</small>
    `;
    container.appendChild(errorDiv);
}

function showChartFallback() {
    const chartContainers = document.querySelectorAll('.chart-container');
    chartContainers.forEach(container => {
        if (!container.querySelector('.chart-error')) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'chart-error';
            errorDiv.innerHTML = `
                <i class="fas fa-exclamation-triangle fa-2x mb-3"></i>
                <div class="fw-bold">Charts are unavailable</div>
                <small class="text-muted">
                    Chart.js library not loaded. Charts are unavailable; the page will try to use CDN fallbacks when possible.
                </small>
            `;
            container.appendChild(errorDiv);
        }
    });
    updateDebugPanel({status: 'fallback', message: 'Chart.js not loaded or invalid data'});
}

// Debug overlay for visual diagnosis (visible to staff/dev only)
function ensureDebugPanel() {
    if (!ADMIN_DASHBOARD_DEBUG) return null;
    if (document.getElementById('dashboard-debug')) return document.getElementById('dashboard-debug');
    const div = document.createElement('div');
    div.id = 'dashboard-debug';
    div.style.position = 'fixed';
    div.style.right = '12px';
    div.style.bottom = '12px';
    div.style.zIndex = 9999;
    div.style.background = 'rgba(0,0,0,0.75)';
    div.style.color = '#fff';
    div.style.fontSize = '12px';
    div.style.padding = '8px 10px';
    div.style.borderRadius = '6px';
    div.style.maxWidth = '360px';
    div.style.maxHeight = '40vh';
    div.style.overflow = 'auto';
    div.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    div.innerHTML = '<b>Dashboard debug</b><div id="dashboard-debug-body" style="margin-top:6px;font-family:monospace;white-space:pre-wrap;"></div>';
    document.body.appendChild(div);
    return div;
}

function updateDebugPanel(obj) {
    if (!ADMIN_DASHBOARD_DEBUG) return;
    try {
        const panel = ensureDebugPanel();
        const body = panel.querySelector('#dashboard-debug-body');
        const lines = [];
        if (obj.status) lines.push('status: ' + obj.status);
        if (obj.info) lines.push('info: ' + JSON.stringify(obj.info));
        if (typeof obj.message !== 'undefined') lines.push('message: ' + obj.message);
        if (obj.error) lines.push('error: ' + obj.error);
        if (obj.raw) lines.push('raw: ' + obj.raw.replace(/\n/g, ' '));
        if (typeof window.Chart !== 'undefined') lines.push('Chart.js loaded: true'); else lines.push('Chart.js loaded: false');
        lines.push('txChart element: ' + (document.getElementById('txChart') ? 'present' : 'missing'));
        lines.push('txPie element: ' + (document.getElementById('txPie') ? 'present' : 'missing'));
        body.textContent = lines.join('\n');
    } catch (e) {
        console.warn('updateDebugPanel error', e);
    }
}

function addInteractiveEffects() {
    // Add hover effects to account rows
    document.querySelectorAll('.account-row').forEach(row => {
        row.addEventListener('mouseenter', function() {
            this.style.transition = 'all 0.2s ease';
            this.classList.add('pulse-on-hover');
        });
        row.addEventListener('mouseleave', function() {
            this.classList.remove('pulse-on-hover');
        });
    });

    // Add click effects to buttons
    document.querySelectorAll('.btn-action, .btn-gradient').forEach(btn => {
        btn.addEventListener('click', function(e) {
            // Add ripple effect
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.cssText = `
                position: absolute;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.7);
                transform: scale(0);
                animation: ripple-animation 0.6s linear;
                width: ${size}px;
                height: ${size}px;
                top: ${y}px;
                left: ${x}px;
                pointer-events: none;
            `;
            
            this.appendChild(ripple);
            setTimeout(() => {
                if (ripple.parentNode) {
                    ripple.parentNode.removeChild(ripple);
                }
            }, 600);
        });
    });
}

// Add ripple animation style globally
if (!document.querySelector('style[data-ripple]')) {
    const rippleStyle = document.createElement('style');
    rippleStyle.setAttribute('data-ripple', 'true');
    rippleStyle.textContent = `
        @keyframes ripple-animation {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
        .btn {
            position: relative;
            overflow: hidden;
        }
    `;
    document.head.appendChild(rippleStyle);
}

// Refresh charts on window resize (with debounce)
let resizeTimer;
window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        const charts = (window.adminCharts && window.adminCharts.length) ? window.adminCharts : [];
        charts.forEach(chart => {
            try { chart.resize(); } catch (e) { /* ignore */ }
        });
    }, 250);
});