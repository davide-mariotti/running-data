// dashboard.js — Ironman Multi-Year Dashboard
// Fetch dinamico basato sull'utente

// State
let rawData = [], filteredData = [];
let activeYears = new Set(), availableYears = [];
let activeSport = 'running', volumeUnit = 'km';
let chartYoY = null, chartEfficiency = null, chartWeekly = null;

Chart.defaults.color = '#8b9bc8';
Chart.defaults.font.family = 'Inter';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

// ── Helpers ───────────────────────────────────────────────
const weekNum = w => parseInt((w || '').replace('W', ''), 10) || 0;

function parseTimeToMin(t) {
    if (!t || typeof t !== 'string') return 0;
    const p = t.split(':').map(Number);
    return p.length === 3 ? p[0]*60 + p[1] + p[2]/60 : p.length === 2 ? p[0] + p[1]/60 : 0;
}

function parsePaceToSec(s) {
    if (!s || typeof s !== 'string') return null;
    const p = s.split(':').map(Number);
    return p.length === 2 && !isNaN(p[0]) && !isNaN(p[1]) ? p[0]*60 + p[1] : null;
}

function formatPace(sec) {
    if (!sec) return '—';
    return `${Math.floor(sec/60)}:${String(Math.round(sec%60)).padStart(2,'0')} /km`;
}

function getDistance(s, sport) {
    if (!s) return 0;
    if (sport === 'swimming') return (s.distanza_m || 0) / 1000;
    return s.distanza_km || s.distanza || 0;
}

function getDurationMin(s) { return parseTimeToMin((s || {}).tempo || (s || {}).tempo_cumulato || ''); }
function getHR(s)     { return (s || {}).fc_media_bpm || 0; }
function getPower(s)  { return (s || {}).potenza_media_w || (s || {}).potenza_media || 0; }
function getSpeed(s)  { return (s || {}).velocita_media_kmh || (s || {}).velocita_media_movimento_kmh || 0; }
function getSwolf(s)  { return (s || {}).swolf_medio || 0; }
function getPace(s) {
    if (!s) return null;
    return parsePaceToSec(s.passo_medio || s.passo_medio_min_km || null);
}

function heatLevel(min) {
    if (min === 0) return 0; if (min < 40) return 1;
    if (min < 80) return 2;  if (min < 120) return 3; return 4;
}

function hrToColor(hr, sport = 'running') {
    if (!hr || hr < 80) return 'rgba(148,163,184,0.7)'; // Sotto zona
    
    let z1, z2, z3, z4;
    if (sport === 'cycling') {
        z1 = 122; z2 = 142; z3 = 157; z4 = 172;
    } else if (sport === 'swimming') {
        z1 = 115; z2 = 135; z3 = 150; z4 = 165;
    } else {
        // running default
        z1 = 130; z2 = 150; z3 = 165; z4 = 180;
    }

    if (hr <= z1) return 'rgba(148,163,184,0.8)'; // ⚪ Z1 Grigio
    if (hr <= z2) return 'rgba(59,130,246,0.8)';  // 🔵 Z2 Blu
    if (hr <= z3) return 'rgba(16,185,129,0.8)';  // 🟢 Z3 Verde
    if (hr <= z4) return 'rgba(249,115,22,0.8)';  // 🟠 Z4 Arancione
    return 'rgba(239,68,68,0.85)';                // 🔴 Z5 Rosso
}

const YEAR_COLORS = [
    { line:'#3b82f6', fill:'rgba(59,130,246,0.15)'  },
    { line:'#f97316', fill:'rgba(249,115,22,0.15)'  },
    { line:'#10b981', fill:'rgba(16,185,129,0.15)'  },
    { line:'#8b5cf6', fill:'rgba(139,92,246,0.15)'  },
];
const SPORT_COLORS = {
    running:  { bg:'rgba(249,115,22,0.75)',  border:'#f97316' },
    cycling:  { bg:'rgba(59,130,246,0.75)',  border:'#3b82f6' },
    swimming: { bg:'rgba(6,182,212,0.75)',   border:'#06b6d4' },
};
const SPORT_LABELS = { running:'🏃 Corsa', cycling:'🚴 Bici', swimming:'🏊 Nuoto' };

// ── Load ──────────────────────────────────────────────────
async function loadData() {
    try {
        if (typeof ATHLETE_USER_ID === 'undefined' || !ATHLETE_USER_ID) {
            console.warn("ATHLETE_USER_ID non ancora impostato, ritento...");
            setTimeout(loadData, 500);
            return;
        }

        if (ATHLETE_USER_ID === 'athlete_main') {
            const res = await fetch('dashboard_index.json');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            rawData = await res.json();
        } else {
            const doc = await db.collection(`athletes/${ATHLETE_USER_ID}/index_data`).doc('dashboard_index').get();
            if (doc.exists && doc.data().data) {
                rawData = JSON.parse(doc.data().data);
            } else {
                console.log("Nessun indice trovato per questo utente.");
                rawData = [];
            }
        }
        
        availableYears = [...new Set(rawData.map(a => a.year))].sort();
        
        // Seleziona l'anno attuale di default, altrimenti l'ultimo disponibile
        const currentYear = new Date().getFullYear().toString();
        if (availableYears.includes(currentYear)) {
            activeYears = new Set([currentYear]);
        } else if (availableYears.length > 0) {
            activeYears = new Set([availableYears[availableYears.length - 1]]);
        }
        
        initFilters();
        applyFilters();
        hideLoading();
    } catch (err) {
        console.error(err);
        document.querySelector('.loading-overlay p').textContent =
            '❌ Errore: avvia un server locale (es. python -m http.server)';
    }
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

// ── Filters ───────────────────────────────────────────────
function initFilters() {
    // Sport buttons
    document.querySelectorAll('.nav-btn[data-sport]').forEach(btn => {
        if (btn.dataset.sport === activeSport) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
        
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-btn[data-sport]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeSport = btn.dataset.sport;
            applyFilters();
        });
    });

    // Volume unit toggle
    document.querySelectorAll('#volumeUnitToggle .toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#volumeUnitToggle .toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            volumeUnit = btn.dataset.unit;
            renderYoYChart();
        });
    });

    // Year buttons (dynamic)
    const container = document.getElementById('yearFilters');
    availableYears.forEach(year => {
        const btn = document.createElement('button');
        btn.className = activeYears.has(year) ? 'year-btn active' : 'year-btn';
        btn.dataset.year = year;
        const count = rawData.filter(a => a.year === year).length;
        btn.innerHTML = `${year} <span class="year-count">${count}</span>`;
        btn.addEventListener('click', () => {
            if (activeYears.has(year)) {
                if (activeYears.size === 1) return;
                activeYears.delete(year); btn.classList.remove('active');
            } else {
                activeYears.add(year); btn.classList.add('active');
            }
            applyFilters();
        });
        container.appendChild(btn);
    });

    // Last update date
    const dates = rawData.map(a => a.date).filter(Boolean).sort();
    if (dates.length) {
        const d = new Date(dates[dates.length - 1]);
        document.getElementById('lastUpdate').textContent =
            d.toLocaleDateString('it-IT', { day:'2-digit', month:'short', year:'numeric' });
    }
}

function applyFilters() {
    filteredData = rawData.filter(a =>
        (activeSport === 'all' || a.sport === activeSport) && activeYears.has(a.year)
    );
    updateKPIs();
    updateHeader();
    renderYoYChart();
    renderEfficiencyChart();
    renderHeatmap();
    renderWeeklyChart();
    updateACWR();
}

// ── ACWR Dinamico ─────────────────────────────────────────
function updateACWR() {
    // Filtro runs per lo sport attivo (senza filtro anno, il carico considera sempre gli ultimi 28gg dalla data più recente)
    const runs = rawData.filter(a => activeSport === 'all' || a.sport === activeSport);
    
    if (!runs.length) return;
    
    const dates = runs.map(r => r.date).filter(Boolean).sort();
    if (!dates.length) return;
    
    const latestDateStr = dates[dates.length - 1];
    const refDate = new Date(latestDateStr + 'T00:00:00');
    
    function formatDateLocal(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    
    const acuteStart = new Date(refDate); acuteStart.setDate(acuteStart.getDate() - 7);
    const chronicStart = new Date(refDate); chronicStart.setDate(chronicStart.getDate() - 28);
    const prevStart = new Date(refDate); prevStart.setDate(prevStart.getDate() - 14);
    
    const acuteStr = formatDateLocal(acuteStart);
    const chronicStr = formatDateLocal(chronicStart);
    const prevStr = formatDateLocal(prevStart);
    
    let acuteKm = 0, chronicKmTotal = 0, prevKm = 0;
    let easyMin = 0, hardMin = 0;
    
    runs.forEach(r => {
        if (!r.date) return;
        const dStr = r.date;
        const dKm = getDistance(r.summary, r.sport);
        const dMin = getDurationMin(r.summary);
        const hr = getHR(r.summary);
        
        if (dStr > chronicStr && dStr <= latestDateStr) {
            chronicKmTotal += dKm;
        }
        if (dStr > acuteStr && dStr <= latestDateStr) {
            acuteKm += dKm;
            if (hr <= 150) easyMin += dMin; 
            else if (hr > 150) hardMin += dMin;
        }
        if (dStr > prevStr && dStr <= acuteStr) {
            prevKm += dKm;
        }
    });
    
    const chronicWeekly = chronicKmTotal / 4;
    const acwr = chronicWeekly > 0 ? (acuteKm / chronicWeekly) : 0;
    const rampRate = prevKm > 0 ? ((acuteKm - prevKm) / prevKm) * 100 : 0;
    const totalMin = easyMin + hardMin;
    const easyPct = totalMin > 0 ? (easyMin / totalMin) * 100 : 0;
    const hardPct = totalMin > 0 ? (hardMin / totalMin) * 100 : 0;
    
    // Aggiorna la UI della dashboard
    const elAcute = document.getElementById('load-acute-km');
    if (elAcute) elAcute.textContent = `${acuteKm.toFixed(1)} km`;
    
    const elChronic = document.getElementById('load-chronic-km');
    if (elChronic) elChronic.textContent = `${chronicWeekly.toFixed(1)} km/sett`;
    
    const elRamp = document.getElementById('load-ramp');
    if (elRamp) elRamp.textContent = `${rampRate >= 0 ? '+' : ''}${rampRate.toFixed(0)}%`;
    
    const elEasy = document.getElementById('load-easy');
    if (elEasy) elEasy.textContent = `${easyPct.toFixed(0)}%`;
    
    const elHard = document.getElementById('load-hard');
    if (elHard) elHard.textContent = `${hardPct.toFixed(0)}%`;
    
    const acwrEl = document.getElementById('load-acwr');
    const acwrStatus = document.getElementById('load-acwr-status');
    const metricLoadVal = document.getElementById('metric-load-value');
    const metricLoadTrend = document.getElementById('metric-load-trend');
    
    if (metricLoadVal) metricLoadVal.textContent = acwr.toFixed(2);
    
    if (acwrEl && acwrStatus) {
        acwrEl.textContent = acwr.toFixed(2);
        if (acwr >= 0.8 && acwr <= 1.3) {
            acwrEl.className = 'load-value load-acwr-value acwr-safe';
            acwrStatus.textContent = '✅ Sicuro';
            acwrStatus.className = 'load-status status-safe';
            if (metricLoadTrend) {
                metricLoadTrend.className = 'metric-trend trend-stable';
                metricLoadTrend.textContent = 'Ottimale';
            }
        } else if (acwr > 1.3 && acwr <= 1.5) {
            acwrEl.className = 'load-value load-acwr-value acwr-warning';
            acwrStatus.textContent = '⚠️ Attenzione';
            acwrStatus.className = 'load-status status-warning';
            if (metricLoadTrend) {
                metricLoadTrend.className = 'metric-trend trend-down';
                metricLoadTrend.textContent = 'Elevato';
            }
        } else {
            acwrEl.className = 'load-value load-acwr-value acwr-danger';
            acwrStatus.textContent = '🔴 Rischio';
            acwrStatus.className = 'load-status status-danger';
            if (metricLoadTrend) {
                metricLoadTrend.className = 'metric-trend trend-down';
                metricLoadTrend.textContent = 'Rischio';
            }
        }
    }
}

// ── KPIs ──────────────────────────────────────────────────
function updateKPIs() {
    let km = 0, min = 0, hrSum = 0, hrN = 0;
    filteredData.forEach(a => {
        const s = a.summary || {};
        km  += getDistance(s, a.sport);
        min += getDurationMin(s);
        const hr = getHR(s);
        if (hr > 0) { hrSum += hr; hrN++; }
    });
    document.getElementById('kpiActivities').textContent = filteredData.length;
    document.getElementById('kpiKm').textContent = km.toFixed(0) + ' km';
    const h = Math.floor(min/60), m = Math.round(min%60);
    document.getElementById('kpiHours').textContent = `${h}h ${m}m`;
    document.getElementById('kpiHr').textContent = hrN ? Math.round(hrSum/hrN) + ' bpm' : '—';
}

function updateHeader() {
    const labels = { all:'Tutti gli sport', running:'Corsa', cycling:'Bici', swimming:'Nuoto' };
    document.getElementById('header-subtitle').textContent =
        `${labels[activeSport]} — ${[...activeYears].sort().join(' • ')}`;
}

// ── Chart 1: YoY Cumulative ───────────────────────────────
function renderYoYChart() {
    const ctx = document.getElementById('chartYoY').getContext('2d');
    if (chartYoY) { chartYoY.destroy(); chartYoY = null; }

    const datasets = [...activeYears].sort().map((year, idx) => {
        const acts = filteredData.filter(a => a.year === year);
        const weekly = {};
        acts.forEach(a => {
            const w = weekNum(a.week);
            if (!w) return;
            const v = volumeUnit === 'km' ? getDistance(a.summary||{}, a.sport) : getDurationMin(a.summary||{})/60;
            weekly[w] = (weekly[w]||0) + v;
        });
        const maxW = Math.max(...Object.keys(weekly).map(Number), 1);
        let cum = 0;
        const data = [];
        for (let w = 1; w <= maxW; w++) { cum += (weekly[w]||0); data.push({ x:w, y:parseFloat(cum.toFixed(1)) }); }
        const c = YEAR_COLORS[idx % YEAR_COLORS.length];
        return { label:year, data, borderColor:c.line, backgroundColor:c.fill, borderWidth:2.5,
                 pointRadius:3, pointHoverRadius:6, tension:0.35, fill:true, parsing:false };
    });

    const unit = volumeUnit === 'km' ? 'km' : 'ore';
    const tooltipOpts = makeTooltipOpts({
        title: items => `Settimana ${items[0].parsed.x}`,
        label: item => ` ${item.dataset.label}: ${item.parsed.y.toFixed(1)} ${unit}`,
    });

    chartYoY = new Chart(ctx, {
        type: 'line', data: { datasets },
        options: {
            responsive:true, maintainAspectRatio:false,
            interaction:{ mode:'index', intersect:false },
            plugins:{ legend: makeLegendOpts(), tooltip: tooltipOpts },
            scales: {
                x:{ type:'linear', title:{ display:true, text:'Settimana', color:'#4a5878', font:{size:11} }, grid:{ color:'rgba(255,255,255,0.04)' }, ticks:{ stepSize:2 } },
                y:{ title:{ display:true, text:`Volume cumulativo (${unit})`, color:'#4a5878', font:{size:11} }, grid:{ color:'rgba(255,255,255,0.04)' } },
            }
        }
    });
}

// ── Chart 2: Aerobic Efficiency (Scatter) ─────────────────
function renderEfficiencyChart() {
    const ctx = document.getElementById('chartEfficiency').getContext('2d');
    if (chartEfficiency) { chartEfficiency.destroy(); chartEfficiency = null; }

    const sport = activeSport === 'all' ? 'running' : activeSport;
    let datasets = [], yLabel = '', subtitle = '', reverseY = false;
    let tooltipCb = {};

    if (sport === 'running') {
        subtitle = 'Passo medio (sec/km) vs Settimana — colore per FC Media (⚪Z1 🔵Z2 🟢Z3 🟠Z4 🔴Z5)';
        yLabel = 'Passo (sec/km) — più basso = più veloce'; reverseY = true;
        tooltipCb = {
            title: items => items[0].raw.name || `Sett. ${items[0].parsed.x}`,
            label: item => [` 📅 ${item.raw.date}`, ` ⚡ ${formatPace(item.parsed.y)}`, ` ❤️ FC: ${item.raw.hr} bpm`],
        };
        const byYear = groupByYear(filteredData.filter(a => a.sport==='running'), a => {
            const pace=getPace(a.summary), w=weekNum(a.week), hr=getHR(a.summary);
            return (pace && w) ? { x:w, y:pace, hr, name:a.name, date:a.date } : null;
        });
        Object.entries(byYear).sort().forEach(([yr, pts], i) => {
            const c = YEAR_COLORS[i % YEAR_COLORS.length];
            datasets.push({ label:`${yr} — Corsa`, data:pts, backgroundColor:pts.map(p=>hrToColor(p.hr, 'running')),
                borderColor:c.line, borderWidth:1, pointRadius:6, pointHoverRadius:9, parsing:false });
        });
    } else if (sport === 'cycling') {
        subtitle = 'Velocità media (km/h) vs Settimana — colore per FC Media (⚪Z1 🔵Z2 🟢Z3 🟠Z4 🔴Z5)';
        yLabel = 'Velocità media (km/h) — più alto = più efficiente'; reverseY = false;
        tooltipCb = {
            title: items => items[0].raw.name || `Sett. ${items[0].parsed.x}`,
            label: item => [` 📅 ${item.raw.date}`, ` 🚴 ${item.parsed.y.toFixed(1)} km/h`, ` ❤️ FC: ${item.raw.hr} bpm`],
        };
        const byYear = groupByYear(filteredData.filter(a => a.sport==='cycling'), a => {
            const spd=getSpeed(a.summary), hr=getHR(a.summary), w=weekNum(a.week);
            return (spd && w) ? { x:w, y:parseFloat(spd.toFixed(1)), hr, name:a.name, date:a.date } : null;
        });
        Object.entries(byYear).sort().forEach(([yr, pts], i) => {
            const c = YEAR_COLORS[i % YEAR_COLORS.length];
            datasets.push({ label:`${yr} — Bici`, data:pts, backgroundColor:pts.map(p=>hrToColor(p.hr, 'cycling')),
                borderColor:c.line, borderWidth:1, pointRadius:6, pointHoverRadius:9, parsing:false });
        });
    } else {
        subtitle = 'SWOLF medio vs Settimana — più basso = più efficiente';
        yLabel = 'SWOLF medio'; reverseY = true;
        tooltipCb = {
            title: items => items[0].raw.name || `Sett. ${items[0].parsed.x}`,
            label: item => [` 📅 ${item.raw.date}`, ` 🌊 SWOLF: ${item.parsed.y}`],
        };
        const byYear = groupByYear(filteredData.filter(a => a.sport==='swimming'), a => {
            const swolf=getSwolf(a.summary), w=weekNum(a.week);
            return (swolf && w) ? { x:w, y:swolf, name:a.name, date:a.date } : null;
        });
        Object.entries(byYear).sort().forEach(([yr, pts], i) => {
            const c = YEAR_COLORS[i % YEAR_COLORS.length];
            datasets.push({ label:`${yr} — Nuoto`, data:pts, backgroundColor:'rgba(6,182,212,0.5)',
                borderColor:'#06b6d4', borderWidth:1.5, pointRadius:6, pointHoverRadius:9, parsing:false });
        });
    }

    document.getElementById('efficiencySubtitle').textContent = subtitle;
    const yTickCb = sport === 'running' ? val => formatPace(val) : val => val;

    chartEfficiency = new Chart(ctx, {
        type: 'scatter', data: { datasets },
        options: {
            responsive:true, maintainAspectRatio:false,
            interaction:{ mode:'nearest', intersect:true },
            plugins:{ legend:makeLegendOpts(), tooltip:makeTooltipOpts(tooltipCb) },
            scales: {
                x:{ type:'linear', title:{ display:true, text:'Settimana', color:'#4a5878', font:{size:11} }, grid:{ color:'rgba(255,255,255,0.04)' } },
                y:{ reverse:reverseY, title:{ display:true, text:yLabel, color:'#4a5878', font:{size:11} }, grid:{ color:'rgba(255,255,255,0.04)' }, ticks:{ callback:yTickCb } },
            }
        }
    });
}

// ── Chart 3: GitHub-style Heatmap ────────────────────────
function renderHeatmap() {
    const wrapper = document.getElementById('heatmapWrapper');
    wrapper.innerHTML = '';

    const dayMap = {};
    rawData.filter(a => activeYears.has(a.year) && a.date).forEach(a => {
        const min = getDurationMin(a.summary || {});
        dayMap[a.date] = (dayMap[a.date] || 0) + min;
    });

    const allDates = rawData.filter(a => activeYears.has(a.year) && a.date).map(a => a.date).sort();
    if (!allDates.length) return;

    const firstDate = new Date(allDates[0]);
    const lastDate  = new Date(allDates[allDates.length - 1]);

    // Align to Monday
    const startDate = new Date(firstDate);
    const d0 = startDate.getDay();
    startDate.setDate(startDate.getDate() + (d0 === 0 ? -6 : 1 - d0));

    const MONTHS = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];
    const DAYS   = ['L','M','M','G','V','S','D'];

    const container = document.createElement('div');
    container.className = 'heatmap-container';

    // Day-of-week label column
    const lblCol = document.createElement('div');
    lblCol.className = 'heatmap-week-col';
    lblCol.style.marginTop = '22px';
    DAYS.forEach(d => {
        const el = document.createElement('div');
        el.style.cssText = 'height:14px;font-size:0.6rem;color:var(--text-3);display:flex;align-items:center;padding-right:4px;';
        el.textContent = d;
        lblCol.appendChild(el);
    });
    container.appendChild(lblCol);

    let cursor = new Date(startDate);
    let curMonth = -1, monthGroup = null, monthDays = null, weekCol = null;

    while (cursor <= lastDate) {
        const mo = cursor.getMonth();
        if (mo !== curMonth) {
            curMonth = mo;
            monthGroup = document.createElement('div');
            monthGroup.className = 'heatmap-month-group';
            const lbl = document.createElement('div');
            lbl.className = 'heatmap-month-label';
            lbl.textContent = `${MONTHS[mo]} ${cursor.getFullYear()}`;
            monthDays = document.createElement('div');
            monthDays.className = 'heatmap-month-days';
            monthGroup.appendChild(lbl);
            monthGroup.appendChild(monthDays);
            container.appendChild(monthGroup);
            weekCol = null;
        }

        const dow = cursor.getDay() === 0 ? 6 : cursor.getDay() - 1; // Mon=0
        if (dow === 0 || weekCol === null) {
            weekCol = document.createElement('div');
            weekCol.className = 'heatmap-week-col';
            if (monthDays.children.length === 0 && dow > 0) {
                for (let i = 0; i < dow; i++) {
                    const blank = document.createElement('div');
                    blank.style.height = '14px';
                    weekCol.appendChild(blank);
                }
            }
            monthDays.appendChild(weekCol);
        }

        const dateStr = cursor.toISOString().split('T')[0];
        const minutes = dayMap[dateStr] || 0;
        const cell = document.createElement('div');
        cell.className = 'heat-cell';
        cell.style.background = `var(--heat-${heatLevel(minutes)})`;
        if (minutes > 0) {
            const hh = Math.floor(minutes/60), mm = Math.round(minutes%60);
            cell.title = `${dateStr}: ${hh}h ${mm}m`;
        } else {
            cell.title = dateStr;
        }
        weekCol.appendChild(cell);
        cursor.setDate(cursor.getDate() + 1);
    }

    wrapper.appendChild(container);
}

// ── Chart 4: Weekly Stacked Bar ───────────────────────────
function renderWeeklyChart() {
    const ctx = document.getElementById('chartWeekly').getContext('2d');
    if (chartWeekly) { chartWeekly.destroy(); chartWeekly = null; }

    const weekSet = new Set();
    filteredData.forEach(a => { if (a.week && a.year) weekSet.add(`${a.year}|${a.week}`); });
    const allWeeks = [...weekSet].sort();
    const labels = allWeeks.map(w => w.split('|')[1]);

    const sportList = activeSport === 'all' ? ['running','cycling','swimming'] : [activeSport];
    const datasets = sportList.map(sport => {
        const { bg, border } = SPORT_COLORS[sport];
        const data = allWeeks.map(wk => {
            const [yr, wn] = wk.split('|');
            const acts = filteredData.filter(a => a.year===yr && a.week===wn && a.sport===sport);
            return parseFloat(acts.reduce((s, a) => s + getDistance(a.summary||{}, sport), 0).toFixed(1));
        });
        return { label:SPORT_LABELS[sport], data, backgroundColor:bg, borderColor:border,
                 borderWidth:1, borderRadius:3, stack:'sports' };
    });

    chartWeekly = new Chart(ctx, {
        type: 'bar', data: { labels, datasets },
        options: {
            responsive:true, maintainAspectRatio:false,
            interaction:{ mode:'index', intersect:false },
            plugins: {
                legend: makeLegendOpts(),
                tooltip: makeTooltipOpts({
                    label: item => ` ${item.dataset.label}: ${item.parsed.y.toFixed(1)} km`,
                    footer: items => {
                        const tot = items.reduce((s, i) => s + i.parsed.y, 0);
                        return tot > 0 ? `  Totale: ${tot.toFixed(1)} km` : null;
                    },
                }),
            },
            scales: {
                x:{ grid:{ color:'rgba(255,255,255,0.04)' }, ticks:{ maxRotation:45, font:{size:10} } },
                y:{ stacked:true, title:{ display:true, text:'Km', color:'#4a5878', font:{size:11} }, grid:{ color:'rgba(255,255,255,0.04)' } },
            }
        }
    });
}

// ── Shared Chart.js config builders ──────────────────────
function makeLegendOpts() {
    return { position:'top', labels:{ color:'#f0f4ff', usePointStyle:true, padding:20, font:{ weight:'600', size:12 } } };
}

function makeTooltipOpts(callbacks = {}) {
    return {
        backgroundColor:'rgba(8,14,26,0.95)', titleColor:'#f0f4ff', bodyColor:'#8b9bc8',
        borderColor:'rgba(255,255,255,0.1)', borderWidth:1, padding:12, cornerRadius:10,
        callbacks,
    };
}

// ── Utility ───────────────────────────────────────────────
function groupByYear(acts, mapFn) {
    const out = {};
    acts.forEach(a => {
        const pt = mapFn(a);
        if (!pt) return;
        if (!out[a.year]) out[a.year] = [];
        out[a.year].push(pt);
    });
    return out;
}

// Boot is now handled by app.js after login
