# 🏃‍♂️ Triathlon & Running Data Dashboard

Benvenuto nel progetto **Running Data**! Questa repository è nata per aiutarti a raccogliere, elaborare e visualizzare i dati dei tuoi allenamenti (Corsa, Bici, Nuoto) esportati da Garmin Connect, trasformandoli in una dashboard interattiva multi-anno e multi-sport, ideale per la preparazione a eventi come un Ironman 70.3.

## ✨ Funzionalità

- **Smistamento Automatico (`organize_inbox.py`)**: Uno script dedicato per organizzare in automatico i file sfusi provenienti da Garmin all'interno di cartelle strutturate per anno e settimana (es. `2026/W01/`), leggendo direttamente la data dai file GPX.
- **Conversione Unificata (`convert_all.py`)**: Un unico script Python per trasformare i file Garmin (CSV e GPX) in JSON. Riconosce lo sport e standardizza metriche molto diverse (come la potenza in bici, o lo SWOLF nel nuoto) sotto un unico formato.
- **Cache Intelligente**: Lo script salta l'elaborazione dei file già convertiti per velocizzare le esecuzioni successive.
- **Dashboard Multi-Anno**: Un'interfaccia dark mode moderna (`dashboard.html`) che legge il `dashboard_index.json` per visualizzare grafici dinamici, curve di volume Anno su Anno, mappe di calore stile GitHub per la costanza, ed efficienza aerobica per ogni sport.

---

## 🛠️ Requisiti

- **Python 3.8+**
- Un web server locale (per visualizzare la dashboard, es: `python -m http.server 8765`)
- Dati esportati da Garmin Connect (CSV "Lap" e file "GPX").

---

## 📂 Struttura della Repository

```text
running-data/
├── dashboard.html/css/js # La dashboard interattiva
├── dashboard_index.json  # Indice globale leggero usato dalla dashboard
├── inbox/                # Cartella di "atterraggio" per i nuovi file scaricati
├── 2026/                 # Cartelle dati grezzi organizzati per anno e settimana
│   └── W01/              
│       ├── activity_123.csv
│       └── activity_123.gpx
├── output2026/           # JSON convertiti pronti per l'uso
│   └── W01/              
│       ├── W01_26-04-01_run_123.json
│       ├── W01_26-04-02_bike_456.json
│       └── W01_26-04-04_swim_789.json
├── organize_inbox.py     # Script che smista i file da inbox/ a ANNO/Wxx/
└── convert_all.py        # Script che processa i dati e aggiorna l'indice
```

---

## 🚀 Guida all'Uso

### 1. Esportazione Dati
1. Vai su **Garmin Connect** web.
2. Apri l'attività e usa l'icona dell'ingranaggio (Impostazioni).
3. Seleziona **Esporta in GPX** e **Esporta Lap in CSV**.
4. Inserisci la coppia di file scaricati direttamente nella cartella `inbox/`.

### 2. Organizzazione File (Automatico)
Dalla cartella root del progetto, esegui:
```bash
python organize_inbox.py
```
Lo script leggerà la data dai file GPX e li sposterà magicamente all'interno della cartella dell'anno e della settimana di calendario corretta (la W01 inizia sempre dal 1° Gennaio).

### 3. Elaborazione Dati e Indice
Esegui la conversione:
```bash
python convert_all.py
```
I file JSON dettagliati verranno creati in `output<ANNO>/<Wxx>/`. Allo stesso tempo il file `dashboard_index.json` verrà aggiornato con tutte le ultime attività.

### 4. Visualizza la Dashboard
Apri un terminale e avvia il server locale:
```bash
python -m http.server 8765
```
Apri il browser su [http://localhost:8765/dashboard.html](http://localhost:8765/dashboard.html) e goditi i tuoi grafici aggiornati!

---

## 💡 Note Tecniche

- **Nomenclatura Output**: I file generati seguono la logica `Wxx_YY-MM-DD_sport_ID.json`. In questo modo, all'interno di ogni cartella settimanale, i file si dispongono sempre in perfetto ordine cronologico dal Lunedì alla Domenica.
- **Mapping Metriche**: `convert_all.py` normalizza le intestazioni CSV Garmin in chiavi `snake_case` e unifica chiavi discordanti tra gli sport per mantenere il `dashboard_index.json` il più flessibile possibile.