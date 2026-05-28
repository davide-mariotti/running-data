#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario dell'Allenatore AI - Generatore di Report Settimanali Incrementale
========================================================================
UTILIZZO:
  1. Assicurati di avere configurato la chiave API in un file `.env`:
     GEMINI_API_KEY=tua_chiave_qui
  2. Esegui lo script:
     python generate_diary.py

FUNZIONALITÀ:
  - Scansiona cronologicamente le cartelle output2024/, output2025/, output2026/ ecc.
  - Per ogni settimana, legge i dati di allenamento dettagliati.
  - Cerca nella cartella `diary/` se il report settimanale esiste già.
  - Se esiste, lo carica in memoria come contesto storico per le settimane successive.
  - Se non esiste, effettua una chiamata a Gemini API includendo lo storico dei precedenti
    report e i dati della settimana corrente per generare un'analisi di coaching progressiva.
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

# --- Configurazione ---
DIARY_DIR = Path("diary")

# Caricamento manuale del file .env per evitare dipendenze esterne
def load_env():
    env_path = Path(".env")
    if not env_path.exists():
        return {}
    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("=", 1)
            if len(parts) == 2:
                env[parts[0].strip()] = parts[1].strip()
    return env

# Helper per formattare i passi (es. corsa)
def format_pace(pace_str):
    return f"{pace_str} min/km" if pace_str else "N/D"

# Estrattore del riassunto e dei giri attivi dell'attività
def parse_activity_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [ERRORE] Impossibile leggere {file_path.name}: {e}")
        return None

    sport = data.get("sport", "running")
    name = data.get("name", "Attività")
    date = data.get("date", "N/D")
    
    # Trova il riassunto (summary)
    summary = data.get("summary")
    laps = data.get("laps", [])
    if not summary and laps:
        for l in laps:
            if l.get("lap") == "Riepilogo" or l.get("intervallo") == "Riepilogo":
                summary = l
                break
        if not summary:
            # Fallback all'ultimo lap se non c'è Riepilogo esplicito
            summary = laps[-1] if laps else {}

    # Estrazione metriche principali
    dist = summary.get("distanza") or summary.get("distanza_km")
    if dist is None and sport == "swimming":
        dist_m = summary.get("distanza_m")
        dist = dist_m / 1000.0 if dist_m is not None else None

    tempo = summary.get("tempo") or summary.get("tempo_cumulato") or "N/D"
    fc_med = summary.get("fc_media_bpm")
    fc_max = summary.get("fc_max_bpm")
    ascesa = summary.get("ascesa_m") or summary.get("ascesa_totale")
    
    # Metriche specifiche
    details = []
    if sport == "running":
        pace = summary.get("passo_medio") or summary.get("passo_medio_in_movimento")
        details.append(f"Passo Medio: {format_pace(pace)}")
        cadenza = summary.get("cadenza_media_pam") or summary.get("cadenza_di_corsa_media")
        if cadenza:
            details.append(f"Cadenza: {cadenza} spm")
    elif sport == "cycling":
        vel = summary.get("velocita_media_kmh") or summary.get("velocita_media")
        details.append(f"Velocità Media: {vel} km/h" if vel else "Velocità: N/D")
        power = summary.get("potenza_media_w") or summary.get("potenza_media")
        if power:
            details.append(f"Potenza Media: {power} W")
    elif sport == "swimming":
        swolf = summary.get("swolf_medio")
        if swolf:
            details.append(f"SWOLF Medio: {swolf}")
        passo_nuoto = summary.get("passo_medio")
        if passo_nuoto:
            details.append(f"Passo Medio Nuoto: {passo_nuoto}/100m")

    # Formatta la descrizione base
    desc = f"- **{name}** ({sport.upper()})\n"
    desc += f"  Data: {date} | Distanza: {f'{dist:.2f} km' if dist is not None else 'N/D'} | Durata: {tempo}\n"
    desc += f"  Cardio: Media {fc_med or 'N/D'} bpm, Max {fc_max or 'N/D'} bpm\n"
    if ascesa:
        desc += f"  Ascesa: {ascesa} m\n"
    if details:
        desc += f"  Metriche: {', '.join(details)}\n"

    # Estrazione di giri significativi (intervalli/ripetute)
    active_laps = []
    for l in laps:
        # Escludi riepilogo, riscaldamento e defaticamento per concentrarci sugli intervalli attivi
        fase = l.get("tipo_di_fase") or ""
        lap_id = l.get("lap") or l.get("intervallo")
        if lap_id == "Riepilogo" or lap_id is None:
            continue
        
        # Filtro per laps attivi (tipicamente in corse a intervalli)
        is_active = False
        if fase in ("Corsa", "Attivo", "Intervallo"):
            is_active = True
        elif isinstance(lap_id, int) and sport == "running" and len(laps) > 3:
            # Se ci sono molti giri numerici, consideriamo quelli con passo elevato o fase non di riposo
            is_active = True

        if is_active:
            l_dist = l.get("distanza") or l.get("distanza_km")
            l_tempo = l.get("tempo")
            l_pace = l.get("passo_medio")
            l_fc = l.get("fc_media_bpm")
            l_power = l.get("potenza_media_w") or l.get("potenza_media")
            
            lap_desc = f"    - Giro {lap_id}: "
            lap_parts = []
            if l_dist: lap_parts.append(f"{l_dist:.2f}km")
            if l_tempo: lap_parts.append(f"Tempo {l_tempo}")
            if l_pace and sport == "running": lap_parts.append(f"Passo {l_pace}")
            if l_fc: lap_parts.append(f"FC {l_fc} bpm")
            if l_power and sport == "cycling": lap_parts.append(f"Potenza {l_power}W")
            
            lap_desc += ", ".join(lap_parts)
            active_laps.append(lap_desc)

    if active_laps:
        desc += "  Giri Attivi/Intervalli:\n" + "\n".join(active_laps) + "\n"

    return desc

# Funzione per chiamare l'API di Gemini
def call_gemini_api(api_key, system_instruction, user_prompt, model_name="gemini-3.5-flash"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": user_prompt}
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {"text": system_instruction}
            ]
        },
        "generationConfig": {
            "temperature": 0.2
        }
    }
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode("utf-8"), 
        headers=headers, 
        method="POST"
    )
    
    retries = 5
    backoff = 2
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                
                # Estrai il testo generato
                candidates = res_json.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text"), res_json.get("usageMetadata", {})
                
                raise Exception(f"Risposta API non valida: {res_body}")
                
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8") if e.fp else ""
            print(f"  [HTTP ERROR {e.code}] {e.reason}")
            
            # Se siamo andati in rate limit (429), aspettiamo e riproviamo
            if e.code == 429 and attempt < retries - 1:
                retry_seconds = 20.0
                try:
                    err_json = json.loads(err_content)
                    details = err_json.get("error", {}).get("details", [])
                    for detail in details:
                        if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                            delay_str = detail.get("retryDelay", "")
                            m = re.search(r"([\d\.]+)", delay_str)
                            if m:
                                retry_seconds = float(m.group(1)) + 1.5
                                break
                except Exception:
                    pass
                
                print(f"  [RATE LIMIT] Limite raggiunto. Attendo {retry_seconds:.1f} secondi come richiesto da Gemini...")
                time.sleep(retry_seconds)
                continue
                
            if err_content:
                print(f"  Dettaglio: {err_content}")
            raise e
        except Exception as e:
            print(f"  [ERRORE DI RETE] {e}")
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise e
            
    return None, {}

def main():
    print("\n" + "="*60)
    print("INIZIALIZZAZIONE DIARIO DELL'ALLENATORE AI")
    print("="*60)

    # 1. Carica configurazione
    env = load_env()
    api_key = env.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "tuo_api_key_qui":
        print("[ERRORE] Chiave API Gemini non trovata.")
        print("Crea un file chiamato `.env` nella root del progetto e aggiungi:")
        print("GEMINI_API_KEY=la_tua_chiave_api_qui")
        print("\nPuoi ottenere una chiave gratuita su https://aistudio.google.com/")
        return

    model_name = env.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash"

    # Crea la cartella diary se non esiste
    DIARY_DIR.mkdir(exist_ok=True)

    # 2. Scansione delle cartelle di output
    base_dir = Path(__file__).parent
    output_dirs = sorted([d for d in base_dir.iterdir() if d.is_dir() and re.match(r"^output\d{4}$", d.name)])

    if not output_dirs:
        print("[ERRORE] Nessuna cartella 'output<ANNO>' trovata. Assicurati di aver eseguito prima 'python convert_all.py'.")
        return

    weeks_to_process = []
    for d in output_dirs:
        year = d.name.replace("output", "")
        for w_dir in d.iterdir():
            if w_dir.is_dir() and re.match(r"^W\d+$", w_dir.name):
                week_num = int(w_dir.name[1:])
                weeks_to_process.append({
                    "year": year,
                    "week_name": w_dir.name,
                    "week_num": week_num,
                    "path": w_dir
                })

    # Ordina cronologicamente per Anno e poi Numero Settimana
    weeks_to_process.sort(key=lambda x: (int(x["year"]), x["week_num"]))
    print(f"[INFO] Trovate {len(weeks_to_process)} settimane convertite.")

    # 3. Carica i report esistenti in memoria
    previous_reports = []
    for wk in weeks_to_process:
        report_file = DIARY_DIR / f"{wk['year']}_{wk['week_name']}_report.md"
        if report_file.exists():
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    content = f.read()
                previous_reports.append({
                    "week_id": f"{wk['year']}_{wk['week_name']}",
                    "content": content
                })
            except Exception as e:
                print(f"  [ERRORE] Lettura del report esistente {report_file.name}: {e}")

    print(f"[INFO] Caricati {len(previous_reports)} report esistenti dal diario.")

    # Gestione modalità Test Settimana Singola
    target_year = env.get("TARGET_YEAR") or os.environ.get("TARGET_YEAR")
    target_week = env.get("TARGET_WEEK") or os.environ.get("TARGET_WEEK")
    
    is_test_mode = False
    if target_year and target_week:
        target_year = target_year.strip()
        target_week = target_week.strip()
        
        # Cerca la settimana target
        target_wk = None
        target_idx = -1
        for idx, wk in enumerate(weeks_to_process):
            if wk["year"] == target_year and wk["week_name"] == target_week:
                target_wk = wk
                target_idx = idx
                break
                
        if target_wk is None:
            print(f"[ERRORE] La settimana specificata {target_year}_{target_week} non è stata trovata nei dati di output.")
            print("Verifica i valori di TARGET_YEAR e TARGET_WEEK in .env.")
            return
            
        print(f"[INFO] Modalità Test Settimana Singola attiva per: {target_year}_{target_week}")
        
        # Filtra previous_reports per tenere solo quelli cronologicamente precedenti
        prev_ids = {f"{w['year']}_{w['week_name']}" for w in weeks_to_process[:target_idx]}
        previous_reports = [r for r in previous_reports if r["week_id"] in prev_ids]
        print(f"[INFO] Storico filtrato: {len(previous_reports)} report precedenti caricati come contesto.")
        
        # Filtra weeks_to_process mantenendo solo la settimana target
        weeks_to_process = [target_wk]
        is_test_mode = True

    # Istruzione di sistema per il coach con background dell'atleta
    system_instruction = (
        "Sei un Coach esperto di Triathlon e Corsa (Ironman Coach). Il tuo compito è redigere il \"Diario dell'Allenatore\" per l'atleta Davide Mariotti.\n"
        "BACKGROUND IMPORTANTE DELL'ATLETA:\n"
        "- Davide parte da ZERO come runner all'inizio del diario (la settimana 2024_W36 rappresenta le sue primissime uscite in assoluto).\n"
        "- Non trattarlo come un atleta esperto fin dall'inizio: il diario deve documentare la sua crescita graduale da principiante a maratoneta e poi triatleta.\n"
        "PROGRESSIONE E OBIETTIVI STORICI DI DAVIDE:\n"
        "  1. 8 Dicembre 2024: Prima Mezza Maratona (corsa senza una vera e propria preparazione specifica).\n"
        "  2. Aprile 2025: Seconda Mezza Maratona (questa volta affrontata con una preparazione strutturata e specifica).\n"
        "  3. 30 Novembre 2025: Prima Maratona Completa (42 km).\n"
        "  4. 29 Marzo 2026: Mezza Maratona.\n"
        "  5. 11 Ottobre 2026: Mezza Maratona.\n"
        "  6. 29 Novembre 2026: Maratona Completa.\n"
        "  7. 2 Maggio 2027: Mezzo Ironman (Ironman 70.3) - questo è il primo obiettivo di triathlon, prima non fa bici/nuoto specifici se non come cross-training sporadico.\n"
        "PARAMETRI FISIOLOGICI DI DAVIDE:\n"
        "- FC Max: 189 bpm\n"
        "- FC a riposo: 44 bpm\n"
        "ZONE CARDIO SPECIFICHE PER SPORT:\n"
        "- Corsa:\n"
        "  * Z1: 120-130 bpm\n"
        "  * Z2: 131-150 bpm\n"
        "  * Z3: 151-165 bpm\n"
        "  * Z4: 166-180 bpm\n"
        "  * Z5: > 180 bpm\n"
        "- Bici:\n"
        "  * Z1: 112-122 bpm\n"
        "  * Z2: 123-142 bpm\n"
        "  * Z3: 143-157 bpm\n"
        "  * Z4: 158-172 bpm\n"
        "  * Z5: > 172 bpm\n"
        "- Nuoto:\n"
        "  * Z1: 105-115 bpm\n"
        "  * Z2: 116-135 bpm\n"
        "  * Z3: 136-150 bpm\n"
        "  * Z4: 151-165 bpm\n"
        "  * Z5: > 165 bpm\n"
        "Il tuo stile deve essere tecnico, analitico e motivante. Analizza i volumi, le frequenze cardio (facendo esplicito riferimento a queste zone per valutare se Davide ha lavorato nel range corretto, ad esempio evidenziando gli allenamenti in Zone 2 come base aerobica o l'intensità degli intervalli), la costanza e la tecnica nei vari sport a seconda della fase di progressione.\n"
        "Fornisci un report settimanale strutturato in Markdown in lingua italiana.\n"
        "IMPORTANTE: Per valutare se l'atleta sta migliorando, peggiorando o se sta accumulando stanchezza, devi confrontare i dati della settimana corrente con lo storico dei report passati. Cita esplicitamente le settimane precedenti (es. \"Rispetto a W36...\") per tracciare il trend."
    )

    # 4. Elaborazione progressiva delle settimane
    processed_count = 0
    
    for wk in weeks_to_process:
        week_id = f"{wk['year']}_{wk['week_name']}"
        report_file = DIARY_DIR / f"{week_id}_report.md"
        
        # Se esiste già, salta (ma NON se siamo in modalità test)
        if report_file.exists() and not is_test_mode:
            continue
            
        print(f"\n--- Generazione Report per {week_id} ---")
        
        # Leggi le attività della settimana corrente
        json_files = sorted(list(wk["path"].glob("*.json")))
        if not json_files:
            print(f"  [WARNING] Nessun file JSON in {wk['path'].name}, salto la settimana.")
            continue
            
        current_week_text = f"ATTIVITÀ DELLA SETTIMANA {week_id}:\n"
        for jf in json_files:
            act_desc = parse_activity_json(jf)
            if act_desc:
                current_week_text += act_desc + "\n"
                
        # Costruisci lo storico delle settimane passate (ultime 15 settimane per non eccedere inutilmente e focalizzarsi sul ciclo di allenamento corrente)
        history_text = ""
        recent_history = previous_reports[-15:]
        if recent_history:
            history_text = "STORICO REPORT PRECEDENTI DELL'ALLENATORE:\n"
            for r in recent_history:
                # Estrai le prime 15 righe o una sintesi per brevità, oppure passalo intero (Gemini gestisce bene)
                history_text += f"\n--- INIZIO REPORT {r['week_id']} ---\n{r['content']}\n--- FINE REPORT {r['week_id']} ---\n"
        else:
            history_text = "Nessun report precedente disponibile. Questo è il primo report del diario.\n"

        # Costruisci il prompt utente
        user_prompt = (
            f"{history_text}\n"
            f"========================================================================\n"
            f"{current_week_text}\n"
            f"========================================================================\n"
            f"Richiesta: Analizza le attività di questa settimana ({week_id}) e redigi il report settimanale dell'allenatore in formato Markdown in lingua italiana. "
            f"Fai un confronto esplicito con i trend e le prestazioni delle settimane precedenti (se presenti nello storico) per valutare i progressi. "
            f"Struttura il report con:\n"
            f"1. Sintesi numerica del volume della settimana (km totali per sport, ore totali, cardio medio)\n"
            f"2. Analisi sport per sport (corsa, bici, nuoto) con andature, cardio ed efficienza aerobica. Discuti anche gli intervalli attivi se presenti.\n"
            f"3. Analisi del trend e dei progressi/punti critici (collegandoti esplicitamente alle settimane precedenti dello storico)\n"
            f"4. Giudizio complessivo del coach (es. Settimana Ottima, Buona, Di Scarico) e indicazioni/consigli concreti per la settimana successiva."
        )

        print(f"  Richiesta inviata a Gemini ({model_name})...")
        try:
            report_content, usage = call_gemini_api(api_key, system_instruction, user_prompt, model_name=model_name)
            if report_content:
                # Salva il file
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(report_content)
                print(f"  [OK] Report salvato in {report_file}")
                
                # Stampa statistiche token
                p_tokens = usage.get("promptTokenCount", 0)
                c_tokens = usage.get("candidatesTokenCount", 0)
                t_tokens = usage.get("totalTokenCount", 0)
                print(f"  [STATS] Token Usati - Input: {p_tokens} | Output: {c_tokens} | Totale: {t_tokens}")
                # AI Studio Free limits per Gemini 3.5 Flash: 1,000,000 TPM
                print(f"  [INFO] Consumato circa il {(t_tokens / 1000000) * 100:.2f}% della quota al minuto (1M TPM) di AI Studio.")
                
                # Aggiungi in memoria per le settimane successive
                previous_reports.append({
                    "week_id": week_id,
                    "content": report_content
                })
                processed_count += 1
                
                # Breve attesa per rispettare i limiti di rate limit gratuiti dell'API
                time.sleep(2)
            else:
                print("  [ERRORE] Nessun contenuto generato dall'API.")
                
        except Exception as e:
            print(f"  [ERRORE CRITICO] Impossibile completare la settimana {week_id}: {e}")
            print("  Interruzione dello script. Risolvi il problema prima di riavviare.")
            break

    print("\n" + "="*60)
    print(f"ELABORAZIONE COMPLETATA. Generati {processed_count} nuovi report.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
