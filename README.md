# 🏃‍♂️ Triathlon & Running Data Dashboard

Benvenuto nel progetto **Running Data**! Questa repository è nata per aiutarti a raccogliere, elaborare e visualizzare i dati dei tuoi allenamenti (Corsa, Bici, Nuoto) esportati da Garmin Connect, trasformandoli in una dashboard interattiva e moderna, ideale per la preparazione a eventi come un Ironman 70.3.

## ✨ Funzionalità

- **Conversione Automatica Unificata**: Un unico script Python per trasformare i file Garmin (CSV per i lap e GPX per i metadati) in file JSON strutturati.
- **Riconoscimento Sport Automatico**: Lo script legge il tag `<type>` dai file GPX per smistare automaticamente gli allenamenti tra corsa, bici e nuoto.
- **Organizzazione Annuale e Settimanale**: Tutti gli allenamenti (a prescindere dallo sport) vengono inseriti nella cartella dell'anno e della settimana corrispondente (es. `2026/W01/`), riflettendo fedelmente la struttura di un piano di allenamento triathlon.
- **Cache Intelligente**: Lo script salta l'elaborazione dei file già convertiti per velocizzare le esecuzioni successive.
- **Output Nominale Individuale**: Per evitare file giganti e ingestibili, lo script genera file JSON snelli e separati per ogni allenamento con la nomenclatura `<Settimana>_<Sport>_<ID>.json` (es. `W04_corsa_12345.json`).

---

## 🛠️ Requisiti

- **Python 3.8+**
- Un web server locale (per visualizzare la dashboard, es: `python -m http.server`)
- Dati esportati da Garmin Connect (CSV "Lap" e GPX).

---

## 📂 Struttura della Repository

```text
running-data/
├── 2026/                 # Cartella principale anno corrente
│   ├── W01/              # Settimana 1 (corsa, bici, nuoto insieme)
│   │   ├── activity_123.csv
│   │   └── activity_123.gpx
│   └── ...
├── output2026/           # JSON generati dallo script
│   ├── W01/              # File json individuali
│   │   ├── W01_corsa_123.json
│   │   ├── W01_bici_456.json
│   │   └── W01_nuoto_789.json
│   └── ...
├── convert_all.py        # Elabora tutte le attività e smista per sport
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

### 2. Organizzazione File (Anno e Settimana)
Aggiungi semplicemente i file appena scaricati nella cartella della settimana di riferimento dentro l'anno corretto (es. `2026/W04/`). Non devi preoccuparti di dividerli per sport, lo script lo farà per te nominandoli automaticamente nel file di output.

### 3. Elaborazione Dati
Dalla cartella root del progetto, esegui:

```bash
python convert_all.py
```

I file JSON verranno creati nella cartella `output2026/`. Lo script scarterà automaticamente quelli già processati in passato basandosi sul nome del file. Ogni allenamento avrà il suo JSON dedicato, compatto e facilmente importabile nel tuo pannello allenamenti.

## 💡 Note Tecniche

- **Nomenclatura Output**: I file vengono salvati automaticamente nel formato `[Settimana]_[sport]_[ID].json`. I nomi degli sport sono stati italianizzati per leggibilità (`corsa`, `bici`, `nuoto`).
- **Mapping**: Lo script Python normalizza le intestazioni dei CSV Garmin (spesso in italiano) in chiavi JSON standard (snake_case), adattandosi alle differenze tra corsa, bici e nuoto.
- **Integrità**: Se un'attività ha solo il GPX o solo il CSV, lo script la salterà segnalando l'errore.