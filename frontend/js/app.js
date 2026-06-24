/**
 * app.js — Logica principale della dashboard.
 *
 * Gestisce autenticazione Firebase, fetch dati Firestore,
 * render delle sezioni e aggiornamento in tempo reale.
 */

// ═══════════════════════════════════════════════════════════════
// 🔧 CONFIGURAZIONE FIREBASE
// ═══════════════════════════════════════════════════════════════
// ⚠️ IMPORTANTE: Sostituisci con i valori dal tuo progetto Firebase
// Li trovi in: Firebase Console → ⚙️ Impostazioni → Generali → Le tue app → Config
const firebaseConfig = {
    apiKey: "AIzaSyDfWh9GWhvfV0vjcsPEt7ZybH3F5LN6Nks",
    authDomain: "agentic-running-coach.firebaseapp.com",
    projectId: "agentic-running-coach",
    storageBucket: "agentic-running-coach.firebasestorage.app",
    messagingSenderId: "410810442087",
    appId: "1:410810442087:web:55c46ad30d775019604fc2",
    measurementId: "G-LEBL4L61KF"
};

// User ID dinamico (impostato al login)
let ATHLETE_USER_ID = "";

// ═══════════════════════════════════════════════════════════════
// 🔥 INIT FIREBASE
// ═══════════════════════════════════════════════════════════════
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();

// ═══════════════════════════════════════════════════════════════
// 🔐 AUTENTICAZIONE
// ═══════════════════════════════════════════════════════════════
const loginScreen = document.getElementById('login-screen');
const dashboard = document.getElementById('app-container');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const btnLogout = document.getElementById('btn-logout');

// Login form handler
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const btnText = document.querySelector('.btn-text');
    const btnLoader = document.querySelector('.btn-loader');

    btnText.style.display = 'none';
    btnLoader.style.display = 'inline';
    loginError.textContent = '';

    try {
        await auth.signInWithEmailAndPassword(email, password);
    } catch (error) {
        loginError.textContent = getAuthErrorMessage(error.code);
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
});

// Logout handler
btnLogout.addEventListener('click', () => {
    auth.signOut();
});

// Google Login handler
const btnGoogle = document.getElementById('btn-google');
if (btnGoogle) {
    btnGoogle.addEventListener('click', async () => {
        const provider = new firebase.auth.GoogleAuthProvider();
        try {
            await auth.signInWithPopup(provider);
        } catch (error) {
            console.error("Google Auth Error:", error);
            loginError.textContent = getAuthErrorMessage(error.code) || `❌ Errore Google: ${error.message}`;
        }
    });
}

// Auth state listener
auth.onAuthStateChanged((user) => {
    if (user) {
        ATHLETE_USER_ID = (user.email === 'davide@mariotti.it') ? 'athlete_main' : user.uid;
        loginScreen.style.display = 'none';
        dashboard.style.display = 'block';
        
        loadDashboardData();
        if (typeof loadData === 'function' && rawData.length === 0) {
            loadData();
        }
        
        // Controlla se l'utente ha inserito le credenziali (se non è l'admin)
        if (ATHLETE_USER_ID !== 'athlete_main') {
            checkUserCredentials(user.uid);
        }
    } else {
        loginScreen.style.display = 'flex';
        dashboard.style.display = 'none';
    }
});

function getAuthErrorMessage(code) {
    const messages = {
        'auth/user-not-found': '❌ Utente non trovato. Crea prima un account in Firebase Console.',
        'auth/wrong-password': '❌ Password errata.',
        'auth/invalid-email': '❌ Email non valida.',
        'auth/too-many-requests': '⏳ Troppi tentativi. Riprova tra qualche minuto.',
        'auth/invalid-credential': '❌ Credenziali non valide. Verifica email e password.',
    };
    return messages[code] || `❌ Errore: ${code}`;
}

// ═══════════════════════════════════════════════════════════════
// 📊 CARICAMENTO DATI
// ═══════════════════════════════════════════════════════════════

async function loadDashboardData() {
    const basePath = `athletes/${ATHLETE_USER_ID}`;
    const today = new Date();
    const historyDaysAgo = new Date(today);
    historyDaysAgo.setDate(today.getDate() - 60);
    const startDate = historyDaysAgo.toISOString().split('T')[0];
    const todayStr = today.toISOString().split('T')[0];

    try {
        // Carica tutto in parallelo
        const [sleepDocs, hrvDocs, batteryDocs, rhrDocs, stressDocs, runsDocs, loadDoc, briefingDocs] =
            await Promise.all([
                fetchCollection(basePath, 'sleep', startDate),
                fetchCollection(basePath, 'hrv', startDate),
                fetchCollection(basePath, 'body_battery', startDate),
                fetchCollection(basePath, 'resting_hr', startDate),
                fetchCollection(basePath, 'stress', startDate),
                fetchCollection(basePath, 'runs', startDate),
                db.collection(`${basePath}/weekly_load`).doc('latest').get(),
                db.collection(`${basePath}/briefings`)
                    .orderBy('date', 'desc')
                    .limit(7)
                    .get(),
            ]);

        // ── Render Metric Cards ──
        renderMetricCards(sleepDocs, hrvDocs, batteryDocs, rhrDocs, stressDocs);

        // ── Render Charts ──
        if (hrvDocs.length > 0) renderHRVChart(hrvDocs);
        if (sleepDocs.length > 0) renderSleepChart(sleepDocs);
        if (batteryDocs.length > 0) renderBatteryChart(batteryDocs);
        if (rhrDocs.length > 0) renderRHRChart(rhrDocs);

        // ── Render Load ──
        // NOTA: il rendering dell'ACWR è ora gestito in modo dinamico da dashboard.js 
        // in base allo sport filtrato (updateACWR).

        // ── Render Activities ──
        renderActivities(runsDocs);

        // ── Render Briefings ──
        const briefings = [];
        briefingDocs.forEach(doc => briefings.push(doc.data()));
        renderBriefings(briefings);

        // ── Render Readiness (latest briefing) ──
        if (briefings.length > 0) {
            renderReadiness(briefings[0]);
        }

        // ── Sync Status ──
        loadSyncStatus();

    } catch (error) {
        console.error('❌ Errore caricamento dati:', error);
    }
}

async function fetchCollection(basePath, collection, startDate) {
    try {
        const snapshot = await db.collection(`${basePath}/${collection}`)
            .where('date', '>=', startDate)
            .orderBy('date', 'asc')
            .get();

        const docs = [];
        snapshot.forEach(doc => docs.push(doc.data()));
        return docs;
    } catch (error) {
        console.warn(`⚠️ Errore fetch ${collection}:`, error);
        return [];
    }
}

// ═══════════════════════════════════════════════════════════════
// 🎯 RENDER: READINESS HERO
// ═══════════════════════════════════════════════════════════════

function renderReadiness(briefing) {
    const badge = document.getElementById('readiness-badge');
    const emoji = document.querySelector('.readiness-emoji');
    const label = document.getElementById('readiness-label');
    const dateEl = document.getElementById('readiness-date');
    const analysis = document.getElementById('readiness-analysis');

    const readiness = (briefing.readiness || 'UNKNOWN').toUpperCase();

    // Remove loading class
    badge.classList.remove('readiness-loading');

    const config = {
        GREEN: { class: 'readiness-green', emoji: '🟢', label: 'GREEN', color: 'var(--green)' },
        AMBER: { class: 'readiness-amber', emoji: '🟡', label: 'AMBER', color: 'var(--amber)' },
        RED: { class: 'readiness-red', emoji: '🔴', label: 'RED', color: 'var(--red)' },
    };

    const cfg = config[readiness] || { class: '', emoji: '⚪', label: readiness, color: 'var(--text-secondary)' };

    badge.className = `readiness-badge ${cfg.class}`;
    emoji.textContent = cfg.emoji;
    label.textContent = cfg.label;
    label.style.color = cfg.color;

    // Date
    if (briefing.date) {
        const d = new Date(briefing.date + 'T00:00:00');
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        dateEl.textContent = `📅 ${d.toLocaleDateString('it-IT', options)}`;
    }

    // Analysis text - format markdown-like content
    if (briefing.analysis) {
        analysis.innerHTML = formatAnalysis(briefing.analysis);
    }
}

function formatAnalysis(text) {
    // Simple markdown-like formatting
    let html = text
        // Bold: **text** or __text__
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/__(.*?)__/g, '<strong>$1</strong>')
        // Headers: lines starting with numbers followed by .
        .replace(/^(\d+\.\s*\*\*.*?\*\*)/gm, '<strong>$1</strong>')
        // Line breaks
        .replace(/\n/g, '<br>');

    return html;
}

// ═══════════════════════════════════════════════════════════════
// 📊 RENDER: METRIC CARDS
// ═══════════════════════════════════════════════════════════════

function renderMetricCards(sleep, hrv, battery, rhr, stress) {
    // Get latest values
    const latestSleep = getLatest(sleep);
    const latestHRV = getLatest(hrv);
    const latestBattery = getLatest(battery);
    const latestRHR = getLatest(rhr);
    const latestStress = getLatest(stress);

    // Sleep
    if (latestSleep) {
        setText('metric-sleep-value', latestSleep.duration_h?.toFixed(1) || '—');
        setText('metric-sleep-sub', `score ${latestSleep.score || '—'}`);
        renderTrend('metric-sleep-trend', sleep, 'score', true);
    }

    // HRV
    if (latestHRV) {
        setText('metric-hrv-value', latestHRV.rmssd || '—');
        setText('metric-hrv-sub', `media ${latestHRV.weekly_avg || '—'} ms`);
        renderTrend('metric-hrv-trend', hrv, 'rmssd', true);
    }

    // Body Battery
    if (latestBattery) {
        setText('metric-battery-value', latestBattery.morning_value || '—');
        setText('metric-battery-sub', `min ${latestBattery.low || '—'} / max ${latestBattery.high || '—'}`);
        renderTrend('metric-battery-trend', battery, 'morning_value', true);
    }

    // Resting HR
    if (latestRHR) {
        setText('metric-rhr-value', latestRHR.value || '—');
        setText('metric-rhr-sub', `baseline ${latestRHR.baseline || '—'} bpm`);
        renderTrend('metric-rhr-trend', rhr, 'value', false); // lower is better
    }

    // Stress
    if (latestStress) {
        setText('metric-stress-value', latestStress.avg_stress || '—');
        setText('metric-stress-sub', `max ${latestStress.max_stress || '—'}`);
        renderTrend('metric-stress-trend', stress, 'avg_stress', false); // lower is better
    }
}

function getLatest(docs) {
    if (!docs || docs.length === 0) return null;
    return docs.sort((a, b) => b.date.localeCompare(a.date))[0];
}

function renderTrend(elementId, docs, field, higherIsBetter) {
    const el = document.getElementById(elementId);
    if (!el || docs.length < 3) return;

    const sorted = docs.sort((a, b) => a.date.localeCompare(b.date));
    const recent = sorted.slice(-3).map(d => d[field]).filter(v => v != null);
    const older = sorted.slice(-7, -3).map(d => d[field]).filter(v => v != null);

    if (recent.length === 0 || older.length === 0) return;

    const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
    const olderAvg = older.reduce((a, b) => a + b, 0) / older.length;
    const diff = recentAvg - olderAvg;
    const pct = ((diff / olderAvg) * 100).toFixed(0);

    const isUp = diff > 0;
    const isGood = higherIsBetter ? isUp : !isUp;
    const isNeutral = Math.abs(diff / olderAvg) < 0.02;

    if (isNeutral) {
        el.className = 'metric-trend trend-stable';
        el.textContent = '→ stabile';
    } else if (isGood) {
        el.className = 'metric-trend trend-up';
        el.textContent = `↑ ${Math.abs(pct)}%`;
    } else {
        el.className = 'metric-trend trend-down';
        el.textContent = `↓ ${Math.abs(pct)}%`;
    }
}

// ═══════════════════════════════════════════════════════════════
// ⚡ RENDER: LOAD SECTION
// ═══════════════════════════════════════════════════════════════

function renderLoadSection(load) {
    setText('load-acute-km', `${load.acute_km?.toFixed(1) || '—'} km`);
    setText('load-chronic-km', `${load.chronic_km_weekly?.toFixed(1) || '—'} km/sett`);
    setText('load-ramp', `${load.ramp_rate_pct >= 0 ? '+' : ''}${load.ramp_rate_pct?.toFixed(0) || '—'}%`);
    setText('load-easy', `${load.easy_pct?.toFixed(0) || '—'}%`);
    setText('load-hard', `${load.hard_pct?.toFixed(0) || '—'}%`);

    // ACWR with color coding
    const acwr = load.acwr;
    const acwrEl = document.getElementById('load-acwr');
    const acwrStatus = document.getElementById('load-acwr-status');

    if (acwr != null) {
        acwrEl.textContent = acwr.toFixed(2);

        if (acwr >= 0.8 && acwr <= 1.3) {
            acwrEl.className = 'load-value load-acwr-value acwr-safe';
            acwrStatus.textContent = '✅ Sicuro';
            acwrStatus.className = 'load-status status-safe';
        } else if (acwr > 1.3 && acwr <= 1.5) {
            acwrEl.className = 'load-value load-acwr-value acwr-warning';
            acwrStatus.textContent = '⚠️ Attenzione';
            acwrStatus.className = 'load-status status-warning';
        } else {
            acwrEl.className = 'load-value load-acwr-value acwr-danger';
            acwrStatus.textContent = '🔴 Rischio';
            acwrStatus.className = 'load-status status-danger';
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// 🏅 RENDER: ACTIVITIES
// ═══════════════════════════════════════════════════════════════

function renderActivities(runs) {
    const container = document.getElementById('activities-list');
    if (!runs || runs.length === 0) {
        container.innerHTML = '<div class="placeholder-text">🏃 Nessuna attività sincronizzata</div>';
        return;
    }

    // Sort by date desc
    const sorted = runs.sort((a, b) => b.date.localeCompare(a.date));

    container.innerHTML = sorted.slice(0, 10).map(run => {
        const d = new Date(run.date + 'T00:00:00');
        const dateStr = d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short' });
        const name = run.name || run.type || 'Corsa';
        const km = run.distance_km?.toFixed(1) || '—';
        const pace = run.avg_pace || '—';
        const hr = run.avg_hr || '—';

        return `
            <div class="activity-row">
                <span class="activity-date">📅 ${dateStr}</span>
                <span class="activity-name">🏃 ${name}</span>
                <span class="activity-stat">
                    <span class="stat-value">${km} km</span>
                    <span class="stat-label">distanza</span>
                </span>
                <span class="activity-stat">
                    <span class="stat-value">${pace}/km</span>
                    <span class="stat-label">pace</span>
                </span>
                <span class="activity-stat">
                    <span class="stat-value">${hr} bpm</span>
                    <span class="stat-label">HR</span>
                </span>
            </div>
        `;
    }).join('');
}

// ═══════════════════════════════════════════════════════════════
// 📋 RENDER: BRIEFING HISTORY
// ═══════════════════════════════════════════════════════════════

function renderBriefings(briefings) {
    const container = document.getElementById('briefing-history');
    if (!briefings || briefings.length === 0) {
        container.innerHTML = '<div class="placeholder-text">📋 Nessun briefing precedente</div>';
        return;
    }

    // Skip the first one (it's shown in the hero)
    const history = briefings.slice(1);
    if (history.length === 0) {
        container.innerHTML = '<div class="placeholder-text">📋 Il primo briefing è mostrato sopra</div>';
        return;
    }

    container.innerHTML = history.map((b, idx) => {
        const readiness = (b.readiness || 'UNKNOWN').toUpperCase();
        const emoji = { GREEN: '🟢', AMBER: '🟡', RED: '🔴' }[readiness] || '⚪';
        const d = new Date(b.date + 'T00:00:00');
        const dateStr = d.toLocaleDateString('it-IT', { weekday: 'short', day: '2-digit', month: 'short' });
        const preview = (b.analysis || '').substring(0, 120).replace(/\n/g, ' ') + '...';
        const fullHtml = formatAnalysis(b.analysis || '');
        const itemId = `briefing-item-${idx}`;

        return `
            <div class="briefing-item" id="${itemId}" onclick="toggleBriefing('${itemId}')">
                <span class="briefing-emoji">${emoji}</span>
                <div class="briefing-info">
                    <div class="briefing-date-label">${dateStr} — ${readiness}</div>
                    <div class="briefing-preview" id="${itemId}-preview">${preview}</div>
                    <div class="briefing-full" id="${itemId}-full" style="display:none; margin-top:8px; line-height:1.5;">${fullHtml}</div>
                </div>
            </div>
        `;
    }).join('');
}

function toggleBriefing(itemId) {
    const previewEl = document.getElementById(`${itemId}-preview`);
    const fullEl = document.getElementById(`${itemId}-full`);
    if (!previewEl || !fullEl) return;

    if (fullEl.style.display === 'none') {
        fullEl.style.display = 'block';
        previewEl.style.display = 'none';
    } else {
        fullEl.style.display = 'none';
        previewEl.style.display = 'block';
    }
}

// ═══════════════════════════════════════════════════════════════
// 🔄 SYNC STATUS
// ═══════════════════════════════════════════════════════════════

async function loadSyncStatus() {
    try {
        const doc = await db.collection('system').doc('last_sync').get();
        if (doc.exists) {
            const data = doc.data();
            const timestamp = data.timestamp?.toDate();
            const status = data.status;

            if (timestamp) {
                const timeStr = timestamp.toLocaleString('it-IT', {
                    day: '2-digit',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit',
                });
                const statusEmoji = status === 'success' ? '✅' : '❌';
                setText('last-sync-text', `${statusEmoji} ${timeStr}`);
            }
        }
    } catch (e) {
        // System collection might not be readable by regular users
        setText('last-sync-text', '⏳ In attesa...');
    }
}

// ═══════════════════════════════════════════════════════════════
// 🔧 UTILITIES
// ═══════════════════════════════════════════════════════════════

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ═══════════════════════════════════════════════════════════════
// ⚙️ GESTIONE CREDENZIALI GARMIN (UTENTI AMICI)
// ═══════════════════════════════════════════════════════════════

const settingsModal = document.getElementById('settings-modal');
const closeSettingsBtn = document.getElementById('close-settings');
const settingsForm = document.getElementById('settings-form');
const settingsMsg = document.getElementById('settings-msg');

function checkUserCredentials(uid) {
    db.collection('users').doc(uid).get()
        .then(doc => {
            if (!doc.exists || !doc.data().garmin_email || !doc.data().garmin_password) {
                // Credenziali mancanti, mostra il modal
                settingsModal.style.display = 'flex';
            }
        })
        .catch(err => {
            console.error("Errore nel recupero credenziali:", err);
        });
}

if (closeSettingsBtn) {
    closeSettingsBtn.addEventListener('click', () => {
        settingsModal.style.display = 'none';
    });
}

if (settingsForm) {
    settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('garmin-email').value.trim();
        const pwd = document.getElementById('garmin-password').value.trim();
        const btn = document.getElementById('btn-save-settings');
        const text = btn.querySelector('.btn-text');
        const loader = btn.querySelector('.btn-loader');
        
        const user = auth.currentUser;
        if (!user) return;
        
        text.style.display = 'none';
        loader.style.display = 'inline-block';
        settingsMsg.textContent = '';
        settingsMsg.style.color = 'var(--green)';
        
        try {
            await db.collection('users').doc(user.uid).set({
                garmin_email: email,
                garmin_password: pwd,
                updated_at: firebase.firestore.FieldValue.serverTimestamp()
            }, { merge: true });
            
            settingsMsg.textContent = 'Credenziali salvate con successo!';
            setTimeout(() => {
                settingsModal.style.display = 'none';
                settingsMsg.textContent = '';
            }, 2000);
            
        } catch (error) {
            console.error("Errore salvataggio credenziali:", error);
            settingsMsg.style.color = 'var(--red)';
            settingsMsg.textContent = 'Errore durante il salvataggio.';
        } finally {
            text.style.display = 'inline-block';
            loader.style.display = 'none';
        }
    });
}
