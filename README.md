# 🏃‍♂️ Running & Training Data Dashboard

Benvenuto nel progetto **Running Data**! Questa repository è nata per aiutarti a raccogliere, elaborare e visualizzare i dati dei tuoi allenamenti (corsa e bici) esportati da Garmin Connect, trasformandoli in una dashboard interattiva e moderna.

## ✨ Funzionalità

- **Conversione Automatica**: Script Python per trasformare i file Garmin (CSV per i lap e GPX per i metadati) in file JSON strutturati.
- **Organizzazione Settimanale**: I dati sono raggruppati per settimana di allenamento (es. W01, W02...), ideale per monitorare piani di preparazione maratona.
- **Dashboard Interattiva**: Visualizzazione dei trend di volume (km totali) e intensità (FC media) tramite grafici dinamici.
- **Supporto Multi-Sport**: Gestione separata per corsa e ciclismo.
- **Dettaglio Attività**: Analisi specifica per ogni sessione, inclusi lap, FC max, cadenza e altro ancora.

---

## 🛠️ Requisiti

- **Python 3.8+**
- Un web server locale (per visualizzare la dashboard, es: `python -m http.server`)
- Dati esportati da Garmin Connect (CSV "Lap" e GPX).

---

## 📂 Struttura della Repository

```text
running-data/
├── 2026-10-29-M/         # Cartella principale dati (es. nome maratona)
│   ├── W01/              # Settimana 1
│   │   ├── activity_123.csv
│   │   └── activity_123.gpx
│   └── ...
├── bike/                 # Dati attività ciclismo
├── output/               # JSON generati dagli script
├── convert_all.py        # Elabora tutte le settimane di corsa
├── convert_week.py       # Elabora una singola settimana specifica
├── convert_bike.py       # Elabora le attività in bici
├── dashboard.html        # Il frontend della dashboard
└── ...
```

---

## 🚀 Guida all'Uso

### 1. Esportazione Dati
Per ogni attività che vuoi includere:
1. Vai su **Garmin Connect** web.
2. Apri l'attività e usa l'icona dell'ingranaggio (Impostazioni).
3. Seleziona **Esporta in GPX**.
4. Seleziona **Esporta Lap in CSV**.
5. Rinomina i file come `activity_<ID>.csv` e `activity_<ID>.gpx` (es. `activity_987654.csv`).

### 2. Organizzazione File
Crea una cartella per la tua preparazione (es. `2026-10-29-M`) e all'interno sottocartelle per le settimane (`W01`, `W02`...). Inserisci i file CSV e GPX nella settimana corrispondente.

### 3. Elaborazione Dati
Dalla cartella root del progetto, esegui:

```bash
# Per elaborare tutto e generare il file per la dashboard
python convert_all.py

# Per elaborare solo le attività in bici
python convert_bike.py
```

I file JSON verranno creati nella cartella `output/`. In particolare, `all_activities.json` è il file principale usato dalla dashboard.

### 4. Visualizzazione Dashboard
A causa delle restrizioni di sicurezza dei browser sui file locali (CORS), la dashboard deve essere servita tramite un server locale:

```bash
# Avvia un server locale
python -m http.server 8000
```

Ora apri il browser su [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html).

---

## 📊 La Dashboard

La dashboard è costruita con **HTML5**, **Vanilla CSS** e **Chart.js**. Offre due viste principali:
1. **Trend Generale**: Un grafico a barre e linee che mostra i km totali settimanali e la frequenza cardiaca media.
2. **Dettaglio Settimanale**: Selezionando una settimana dal menu a tendina, puoi vedere la distanza e l'intensità di ogni singolo allenamento di quel periodo.

---

## 💡 Note Tecniche

- **Mapping**: Gli script Python normalizzano le intestazioni dei CSV Garmin (spesso in italiano) in chiavi JSON standard (snake_case).
- **Integrità**: Se un'attività ha solo il GPX o solo il CSV, lo script la salterà segnalando l'errore.