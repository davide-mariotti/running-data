/**
 * charts.js — Componenti grafici per la dashboard biometrica.
 *
 * Usa Chart.js per creare grafici a linee eleganti in dark mode
 * per HRV, Sleep, Body Battery e Resting HR.
 */

// ── Chart.js Global Config ──────────────────────────────────
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.animation.duration = 800;
Chart.defaults.animation.easing = 'easeOutQuart';

// ── Color Palette ───────────────────────────────────────────
const CHART_COLORS = {
    indigo: { line: '#818cf8', fill: 'rgba(129, 140, 248, 0.08)', point: '#a5b4fc' },
    green:  { line: '#4ade80', fill: 'rgba(74, 222, 128, 0.08)', point: '#86efac' },
    amber:  { line: '#fbbf24', fill: 'rgba(251, 191, 36, 0.08)', point: '#fcd34d' },
    red:    { line: '#f87171', fill: 'rgba(248, 113, 113, 0.08)', point: '#fca5a5' },
    cyan:   { line: '#22d3ee', fill: 'rgba(34, 211, 238, 0.08)', point: '#67e8f9' },
};

// ── Store chart instances for cleanup ───────────────────────
const chartInstances = {};

/**
 * Crea la configurazione base per un grafico a linee.
 */
function createLineConfig(labels, data, color, options = {}) {
    return {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                borderColor: color.line,
                backgroundColor: color.fill,
                pointBackgroundColor: color.point,
                pointBorderColor: color.line,
                pointRadius: 4,
                pointHoverRadius: 7,
                borderWidth: 2.5,
                fill: true,
                tension: 0.35,
                spanGaps: true,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.03)',
                        drawBorder: false,
                    },
                    ticks: {
                        maxTicksLimit: 7,
                        font: { size: 10 },
                    },
                },
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.03)',
                        drawBorder: false,
                    },
                    ticks: {
                        font: { size: 10 },
                    },
                    ...(options.yMin !== undefined ? { min: options.yMin } : {}),
                    ...(options.yMax !== undefined ? { max: options.yMax } : {}),
                },
            },
            plugins: {
                tooltip: {
                    backgroundColor: 'rgba(13, 13, 26, 0.95)',
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: function(ctx) {
                            const suffix = options.suffix || '';
                            return `${ctx.parsed.y}${suffix}`;
                        },
                    },
                },
            },
        },
    };
}

/**
 * Renderizza (o aggiorna) un grafico nel canvas specificato.
 */
function renderChart(canvasId, labels, data, color, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // Distruggi istanza precedente se esiste
    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    const config = createLineConfig(labels, data, color, options);
    chartInstances[canvasId] = new Chart(canvas, config);
}

/**
 * Formatta una data ISO in formato breve (es. "14 Giu").
 */
function formatDateShort(dateStr) {
    const months = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getDate()} ${months[d.getMonth()]}`;
}

// ── Render Functions per ogni metrica ───────────────────────

/**
 * 💓 Grafico HRV (RMSSD) - ultimi 14 giorni
 */
function renderHRVChart(docs) {
    const sorted = docs.sort((a, b) => a.date.localeCompare(b.date));
    const labels = sorted.map(d => formatDateShort(d.date));
    const data = sorted.map(d => d.rmssd || null);
    renderChart('chart-hrv', labels, data, CHART_COLORS.indigo, { suffix: ' ms' });
}

/**
 * 💤 Grafico Sleep Score - ultimi 14 giorni
 */
function renderSleepChart(docs) {
    const sorted = docs.sort((a, b) => a.date.localeCompare(b.date));
    const labels = sorted.map(d => formatDateShort(d.date));
    const data = sorted.map(d => d.score || null);
    renderChart('chart-sleep', labels, data, CHART_COLORS.cyan, {
        suffix: '',
        yMin: 0,
        yMax: 100,
    });
}

/**
 * 🔋 Grafico Body Battery (valore mattutino) - ultimi 14 giorni
 */
function renderBatteryChart(docs) {
    const sorted = docs.sort((a, b) => a.date.localeCompare(b.date));
    const labels = sorted.map(d => formatDateShort(d.date));
    const data = sorted.map(d => d.morning_value || null);
    renderChart('chart-battery', labels, data, CHART_COLORS.green, {
        suffix: '',
        yMin: 0,
        yMax: 100,
    });
}

/**
 * ❤️ Grafico Resting HR - ultimi 14 giorni
 */
function renderRHRChart(docs) {
    const sorted = docs.sort((a, b) => a.date.localeCompare(b.date));
    const labels = sorted.map(d => formatDateShort(d.date));
    const data = sorted.map(d => d.value || null);
    renderChart('chart-rhr', labels, data, CHART_COLORS.red, { suffix: ' bpm' });
}
