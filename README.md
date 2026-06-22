# 🏃 Agentic Running Coach

Un coach per l'endurance completamente autonomo basato su AI. Questo progetto estrae ogni giorno i dati biometrici e di carico da Garmin Connect, li storicizza su Firestore e utilizza un agente Gemini AI per valutare la prontezza fisica. L'AI percepisce la fatica, analizza i trend e ti dice come stai — ogni mattina, senza chiederlo.

## 🏗️ Architettura

```
Garmin Connect → [Cloud Function 🌙 03:00] → Firestore → [Cloud Function ☀️ 06:30] → Gemini AI → Dashboard
```

- **🌙 Nightly Sync (03:00)**: Estrae sleep, HRV, Body Battery, stress, resting HR e attività
- **☀️ Morning Coach (06:30)**: Analizza 14 giorni di dati e genera il briefing di readiness
- **📊 Dashboard**: Web app moderna per visualizzare tutto

## 📦 Stack Tecnologico

| Componente | Tecnologia |
|-----------|-----------|
| **Database** | Firebase Firestore |
| **Backend** | Firebase Cloud Functions (Python 3.12) |
| **AI** | Google Gemini 2.5 Flash |
| **Data Source** | Garmin Connect via `python-garminconnect` |
| **Frontend** | Vanilla HTML/CSS/JS + Chart.js |
| **Hosting** | Firebase Hosting |
| **Auth** | Firebase Authentication |

## 🚀 Quick Start

### Prerequisiti

- Python 3.11+
- Node.js 18+
- Account Firebase con piano Blaze
- Account Garmin Connect
- API Key Gemini ([aistudio.google.com](https://aistudio.google.com/apikey))

### 1. Setup Firebase

```bash
npm install -g firebase-tools
firebase login
firebase init  # Seleziona: Firestore, Functions (Python), Hosting
```

### 2. Configura i segreti

```bash
firebase functions:secrets:set GARMIN_EMAIL
firebase functions:secrets:set GARMIN_PASSWORD
firebase functions:secrets:set GEMINI_API_KEY
```

### 3. Setup iniziale Garmin

```bash
cd scripts
pip install garminconnect firebase-admin
python setup_garmin.py
```

### 4. Configura la Dashboard

1. Vai su Firebase Console → ⚙️ → Le tue app → Aggiungi app web
2. Copia il `firebaseConfig` in `hosting/js/app.js`
3. Attiva Authentication → Email/Password
4. Crea un utente nella console

### 5. Deploy

```bash
firebase deploy
```

## 📁 Struttura Progetto

```
├── functions/
│   ├── main.py              # Entry point Cloud Functions
│   ├── garmin_sync.py        # Pipeline dati Garmin Connect
│   ├── coach_brain.py        # Agente AI readiness
│   ├── prompts.py            # System prompt + templates
│   ├── compute_load.py       # Calcolo ACWR e carico
│   └── requirements.txt
├── hosting/
│   ├── index.html            # Dashboard SPA
│   ├── css/style.css         # Design system (dark mode)
│   └── js/
│       ├── app.js            # Logica Firebase + rendering
│       └── charts.js         # Grafici biometrici
├── scripts/
│   └── setup_garmin.py       # Setup iniziale interattivo
├── firebase.json
├── firestore.rules
└── firestore.indexes.json
```

## 🤖 Come funziona il Coach

Ogni mattina l'agente Gemini riceve una tabella con 14 giorni di dati biometrici e restituisce:

| Sezione | Cosa dice |
|---------|----------|
| 🎯 **READINESS** | GREEN / AMBER / RED con i numeri chiave |
| 📈 **TREND** | Direzione di HRV, sleep, Body Battery, resting HR |
| ⚡ **CARICO** | ACWR, km, ramp rate |
| 🔍 **SEGNALI** | Pattern preoccupanti nei dati |
| 💡 **CONSIGLIO** | Raccomandazione concreta |
| 🚩 **FLAG** | Allarmi urgenti |

## 📊 Dati Estratti da Garmin

| Metrica | Fonte Garmin | Frequenza |
|---------|-------------|-----------|
| 💤 Sleep | `get_sleep_data()` | Giornaliera |
| 💓 HRV | `get_hrv_data()` | Giornaliera |
| 🔋 Body Battery | `get_body_battery()` | Giornaliera |
| 😰 Stress | `get_stress_data()` | Giornaliera |
| ❤️ Resting HR | `get_rhr_day()` | Giornaliera |
| 🏃 Attività | `get_activities_by_date()` | Giornaliera |

## 💰 Costi

**$0/mese** con le quote gratuite di Firebase Blaze e Gemini API.

## 📄 Licenza

Progetto personale ispirato alla guida [Running on AI — The Iceberg Guide](https://runningon.ai).
