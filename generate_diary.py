#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diario dell'Allenatore AI - Generatore di Report Settimanali
=============================================================
UTILIZZO:
  1. Assicurati di avere configurato la chiave API in un file `.env`:
     GEMINI_API_KEY=tua_chiave_qui
     GEMINI_MODEL=gemini-2.5-pro  (opzionale, default: gemini-2.5-pro)
  2. Per generare solo una settimana specifica, aggiungi al .env:
     TARGET_YEAR=2026
     TARGET_WEEK=W22
  3. Esegui lo script:
     python generate_diary.py

FUNZIONALITÀ:
  - Scansiona cronologicamente le cartelle output2024/, output2025/, output2026/
  - Per ogni settimana, estrae TUTTE le metriche Garmin (TCS, bilanciamento,
    oscillazione verticale, cadenza, FC per giro, potenza, ecc.)
  - Genera analisi individuale per ogni singolo allenamento
  - Per le settimane PASSATE: omette i consigli per la settimana successiva
  - Per le settimane FUTURE: include indicazioni concrete
  - Usa Gemini 2.5 Pro (il modello top di Google con reasoning esteso)
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date

# --- Configurazione ---
DIARY_DIR = Path("diary")

# -------------------------------------------------------------------------
# Caricamento .env
# -------------------------------------------------------------------------
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

# -------------------------------------------------------------------------
# Rilevamento settimana passata
# -------------------------------------------------------------------------
def is_past_week(year: int, week_num: int) -> bool:
    """Restituisce True se la settimana ISO è già trascorsa rispetto ad oggi."""
    today = date.today()
    current_year, current_week, _ = today.isocalendar()
    if year < current_year:
        return True
    if year == current_year and week_num < current_week:
        return True
    return False

# -------------------------------------------------------------------------
# Estrazione metriche complete dal JSON Garmin
# -------------------------------------------------------------------------
def parse_activity_json(file_path):
    """
    Legge un file JSON Garmin e restituisce un dizionario strutturato
    con TUTTE le metriche disponibili (summary + giri dettagliati).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [ERRORE] Impossibile leggere {file_path.name}: {e}")
        return None

    sport = data.get("sport", "running")
    name = data.get("name", "Attività")
    activity_date = data.get("date", "N/D")
    activity_id = data.get("activity_id", "")

    # Trova il riassunto (summary)
    summary = data.get("summary")
    laps = data.get("laps", [])

    if not summary and laps:
        for lap in laps:
            if lap.get("lap") == "Riepilogo" or lap.get("intervallo") == "Riepilogo":
                summary = lap
                break
        if not summary:
            summary = laps[-1] if laps else {}

    if not summary:
        summary = {}

    # Helper per ottenere un valore con fallback multipli
    def get_val(*keys):
        for k in keys:
            v = summary.get(k)
            if v is not None:
                return v
        return None

    # --- Distanza ---
    dist = get_val("distanza", "distanza_km")
    if dist is None and sport == "swimming":
        dist_m = get_val("distanza_m")
        dist = dist_m / 1000.0 if dist_m is not None else None

    # --- Metriche comuni ---
    parsed = {
        "sport": sport,
        "name": name,
        "date": activity_date,
        "activity_id": activity_id,
        "summary": {
            "distanza_km": dist,
            "tempo": get_val("tempo", "tempo_cumulato"),
            "tempo_in_movimento": get_val("tempo_in_movimento"),
            "fc_media_bpm": get_val("fc_media_bpm"),
            "fc_max_bpm": get_val("fc_max_bpm"),
            "ascesa_m": get_val("ascesa_m", "ascesa_totale"),
            "discesa_m": get_val("discesa_m"),
            "calorie": get_val("calorie"),
            "temperatura_med": get_val("temperatura_med"),
        },
        "laps": [],
    }

    # --- Metriche specifiche per sport ---
    if sport == "running":
        parsed["summary"].update({
            "passo_medio": get_val("passo_medio"),
            "passo_medio_in_movimento": get_val("passo_medio_in_movimento"),
            "prp_medio": get_val("prp_medio"),
            "potenza_media_w": get_val("potenza_media_w", "potenza_media"),
            "potenza_max_w": get_val("potenza_max_w", "potenza_max"),
            "wkg_medio": get_val("wkg_medio"),
            "wkg_massimo": get_val("wkg_massimo"),
            "cadenza_media_pam": get_val("cadenza_media_pam", "cadenza_di_corsa_media"),
            "cadenza_max_pam": get_val("cadenza_max_pam"),
            "contatto_suolo_ms": get_val("contatto_suolo_ms"),
            "bilanciamento_tcs": get_val("bilanciamento_tcs"),
            "lunghezza_passo_m": get_val("lunghezza_passo_m"),
            "oscillazione_verticale_cm": get_val("oscillazione_verticale_cm"),
            "rapporto_verticale_pct": get_val("rapporto_verticale_pct"),
            "perdita_velocita_cms": get_val("perdita_velocita_cms"),
            "perdita_velocita_pct": get_val("perdita_velocita_pct"),
            "passo_migliore": get_val("passo_migliore"),
        })
    elif sport == "cycling":
        parsed["summary"].update({
            "velocita_media_kmh": get_val("velocita_media_kmh", "velocita_media"),
            "velocita_max_kmh": get_val("velocita_max_kmh", "velocita_max"),
            "potenza_media_w": get_val("potenza_media_w", "potenza_media"),
            "potenza_max_w": get_val("potenza_max_w", "potenza_max"),
            "wkg_medio": get_val("wkg_medio"),
            "wkg_massimo": get_val("wkg_massimo"),
            "cadenza_media_rpm": get_val("cadenza_media_rpm", "cadenza_media"),
            "cadenza_max_rpm": get_val("cadenza_max_rpm"),
        })
    elif sport == "swimming":
        parsed["summary"].update({
            "passo_medio": get_val("passo_medio"),
            "swolf_medio": get_val("swolf_medio"),
            "bracciate_per_vasca": get_val("bracciate_per_vasca", "bracciate_media"),
            "distanza_per_bracciata_m": get_val("distanza_per_bracciata_m"),
            "distanza_m": get_val("distanza_m"),
        })

    # --- Giri dettagliati ---
    for lap in laps:
        lap_id = lap.get("lap") or lap.get("intervallo")
        if lap_id == "Riepilogo" or lap_id is None:
            continue

        lap_data = {
            "lap_id": lap_id,
            "tipo_di_fase": lap.get("tipo_di_fase", ""),
            "tempo": lap.get("tempo"),
            "tempo_cumulato": lap.get("tempo_cumulato"),
            "distanza_km": lap.get("distanza") or lap.get("distanza_km"),
            "fc_media_bpm": lap.get("fc_media_bpm"),
            "fc_max_bpm": lap.get("fc_max_bpm"),
            "ascesa_m": lap.get("ascesa_m"),
            "discesa_m": lap.get("discesa_m"),
            "calorie": lap.get("calorie"),
            "temperatura_med": lap.get("temperatura_med"),
        }

        if sport == "running":
            lap_data.update({
                "passo_medio": lap.get("passo_medio"),
                "passo_medio_in_movimento": lap.get("passo_medio_in_movimento"),
                "prp_medio": lap.get("prp_medio"),
                "potenza_media_w": lap.get("potenza_media_w") or lap.get("potenza_media"),
                "potenza_max_w": lap.get("potenza_max_w") or lap.get("potenza_max"),
                "wkg_medio": lap.get("wkg_medio"),
                "cadenza_media_pam": lap.get("cadenza_media_pam"),
                "cadenza_max_pam": lap.get("cadenza_max_pam"),
                "contatto_suolo_ms": lap.get("contatto_suolo_ms"),
                "bilanciamento_tcs": lap.get("bilanciamento_tcs"),
                "lunghezza_passo_m": lap.get("lunghezza_passo_m"),
                "oscillazione_verticale_cm": lap.get("oscillazione_verticale_cm"),
                "rapporto_verticale_pct": lap.get("rapporto_verticale_pct"),
                "perdita_velocita_cms": lap.get("perdita_velocita_cms"),
                "perdita_velocita_pct": lap.get("perdita_velocita_pct"),
            })
        elif sport == "cycling":
            lap_data.update({
                "velocita_media_kmh": lap.get("velocita_media_kmh") or lap.get("velocita_media"),
                "potenza_media_w": lap.get("potenza_media_w") or lap.get("potenza_media"),
                "potenza_max_w": lap.get("potenza_max_w") or lap.get("potenza_max"),
                "wkg_medio": lap.get("wkg_medio"),
                "cadenza_media_rpm": lap.get("cadenza_media_rpm") or lap.get("cadenza_media"),
            })
        elif sport == "swimming":
            lap_data.update({
                "passo_medio": lap.get("passo_medio"),
                "swolf": lap.get("swolf") or lap.get("swolf_medio"),
                "bracciate": lap.get("bracciate") or lap.get("bracciate_per_vasca"),
                "tipo_vasca": lap.get("tipo_vasca"),
            })

        parsed["laps"].append(lap_data)

    return parsed

# -------------------------------------------------------------------------
# Formattazione del testo di attività per il prompt
# -------------------------------------------------------------------------
def build_activity_prompt_text(act: dict) -> str:
    """
    Converte il dizionario di un'attività in un testo ricco e strutturato
    per l'invio al modello AI.
    """
    s = act["summary"]
    sport = act["sport"].upper()
    lines = []

    dist_str = f"{s['distanza_km']:.2f} km" if s.get("distanza_km") is not None else "N/D"
    lines.append(f"### ATTIVITÀ: {act['name']} ({sport})")
    lines.append(f"- **Data:** {act['date']} | **Distanza:** {dist_str} | **Durata:** {s.get('tempo') or 'N/D'}", )

    # Temperatura e calorie
    extras = []
    if s.get("temperatura_med") is not None:
        extras.append(f"Temp: {s['temperatura_med']}°C")
    if s.get("calorie") is not None:
        extras.append(f"Calorie: {s['calorie']}")
    if extras:
        lines[-1] += " | " + " | ".join(extras)

    # FC
    fc_med = s.get("fc_media_bpm")
    fc_max = s.get("fc_max_bpm")
    if fc_med or fc_max:
        lines.append(f"- **Frequenza Cardiaca:** Media {fc_med or 'N/D'} bpm | Max {fc_max or 'N/D'} bpm")

    # Ascesa/discesa
    if s.get("ascesa_m"):
        disc_str = f" | Discesa: {s['discesa_m']} m" if s.get("discesa_m") else ""
        lines.append(f"- **Dislivello:** Ascesa {s['ascesa_m']} m{disc_str}")

    # --- Metriche specifiche per sport ---
    if act["sport"] == "running":
        if s.get("passo_medio"):
            mov_str = f" | In Movimento: {s['passo_medio_in_movimento']} min/km" if s.get("passo_medio_in_movimento") else ""
            lines.append(f"- **Passo Medio:** {s['passo_medio']} min/km{mov_str}")

        if s.get("potenza_media_w") is not None:
            wkg_str = f" ({s['wkg_medio']} W/kg)" if s.get("wkg_medio") else ""
            pow_max_str = f" | Max: {s['potenza_max_w']} W" if s.get("potenza_max_w") else ""
            lines.append(f"- **Potenza:** Media {s['potenza_media_w']} W{wkg_str}{pow_max_str}")

        if s.get("cadenza_media_pam") is not None:
            cad_max_str = f" | Max: {s['cadenza_max_pam']} spm" if s.get("cadenza_max_pam") else ""
            lines.append(f"- **Cadenza:** Media {s['cadenza_media_pam']} spm{cad_max_str}  *(target élite: 175-185 spm)*")

        if s.get("contatto_suolo_ms") is not None:
            lines.append(f"- **TCS (Tempo Contatto Suolo):** {s['contatto_suolo_ms']} ms  *(target: <250ms élite, 250-270 buono)*")

        if s.get("bilanciamento_tcs"):
            lines.append(f"- **Bilanciamento TCS:** {s['bilanciamento_tcs']}  *(ideale: 50/50 — asimmetrie >1.5% da segnalare)*")

        if s.get("oscillazione_verticale_cm") is not None:
            rv_str = f" | Rapporto Verticale: {s['rapporto_verticale_pct']}%" if s.get("rapporto_verticale_pct") else ""
            lines.append(f"- **Oscillazione Verticale:** {s['oscillazione_verticale_cm']} cm{rv_str}  *(target: <8.0cm ottimo, 8-9 buono, >9 elevato)*")

        if s.get("lunghezza_passo_m") is not None:
            lines.append(f"- **Lunghezza Passo:** {s['lunghezza_passo_m']} m")

        if s.get("perdita_velocita_cms") is not None:
            lines.append(f"- **Perdita Velocità:** {s['perdita_velocita_cms']} cm/s ({s.get('perdita_velocita_pct')}%)")

    elif act["sport"] == "cycling":
        if s.get("velocita_media_kmh") is not None:
            lines.append(f"- **Velocità:** Media {s['velocita_media_kmh']} km/h | Max: {s.get('velocita_max_kmh') or 'N/D'} km/h")
        if s.get("potenza_media_w") is not None:
            wkg_str = f" ({s['wkg_medio']} W/kg)" if s.get("wkg_medio") else ""
            lines.append(f"- **Potenza:** Media {s['potenza_media_w']} W{wkg_str} | Max: {s.get('potenza_max_w') or 'N/D'} W  *(FTP: da definire)*")
        if s.get("cadenza_media_rpm") is not None:
            lines.append(f"- **Cadenza:** Media {s['cadenza_media_rpm']} RPM  *(target agilità: 85-95 RPM)*")

    elif act["sport"] == "swimming":
        if s.get("passo_medio"):
            lines.append(f"- **Passo Medio:** {s['passo_medio']}/100m")
        if s.get("swolf_medio") is not None:
            lines.append(f"- **SWOLF Medio:** {s['swolf_medio']}  *(target: <40 ottimo, 40-45 buono, >50 da migliorare)*")
        if s.get("bracciate_per_vasca") is not None:
            lines.append(f"- **Bracciate/Vasca:** {s['bracciate_per_vasca']}")
        if s.get("distanza_per_bracciata_m") is not None:
            lines.append(f"- **Distanza/Bracciata:** {s['distanza_per_bracciata_m']} m")

    # --- Tabella giri (running e cycling) ---
    laps = act.get("laps", [])
    if laps and act["sport"] in ("running", "cycling"):
        lines.append("")
        lines.append("**ANALISI GIRO PER GIRO** (deriva cardiaca, progressione, qualità recuperi):")

        if act["sport"] == "running":
            # Header tabella running
            lines.append("| Giro | Dist | Passo | FC Med | FC Max | Cad | TCS | Bil.TCS | Osc.V | Potenza |")
            lines.append("|------|------|-------|--------|--------|-----|-----|---------|-------|---------|")
            for lap in laps:
                lap_id = lap.get("lap_id", "?")
                dist_l = f"{lap['distanza_km']:.2f}km" if lap.get("distanza_km") is not None else "-"
                passo = lap.get("passo_medio") or "-"
                fc_m = f"{lap['fc_media_bpm']}bpm" if lap.get("fc_media_bpm") else "-"
                fc_x = f"{lap['fc_max_bpm']}bpm" if lap.get("fc_max_bpm") else "-"
                cad = f"{lap['cadenza_media_pam']}spm" if lap.get("cadenza_media_pam") else "-"
                tcs = f"{lap['contatto_suolo_ms']}ms" if lap.get("contatto_suolo_ms") else "-"
                bil = lap.get("bilanciamento_tcs") or "-"
                osc = f"{lap['oscillazione_verticale_cm']}cm" if lap.get("oscillazione_verticale_cm") else "-"
                pow_l = f"{lap['potenza_media_w']}W" if lap.get("potenza_media_w") else "-"
                fase = f" ({lap['tipo_di_fase']})" if lap.get("tipo_di_fase") else ""
                lines.append(f"| {lap_id}{fase} | {dist_l} | {passo} | {fc_m} | {fc_x} | {cad} | {tcs} | {bil} | {osc} | {pow_l} |")

        elif act["sport"] == "cycling":
            lines.append("| Giro | Dist | Velocità | FC Med | FC Max | Cad | Potenza |")
            lines.append("|------|------|----------|--------|--------|-----|---------|")
            for lap in laps:
                lap_id = lap.get("lap_id", "?")
                dist_l = f"{lap['distanza_km']:.2f}km" if lap.get("distanza_km") is not None else "-"
                vel = f"{lap['velocita_media_kmh']}km/h" if lap.get("velocita_media_kmh") else "-"
                fc_m = f"{lap['fc_media_bpm']}bpm" if lap.get("fc_media_bpm") else "-"
                fc_x = f"{lap['fc_max_bpm']}bpm" if lap.get("fc_max_bpm") else "-"
                cad = f"{lap['cadenza_media_rpm']}RPM" if lap.get("cadenza_media_rpm") else "-"
                pow_l = f"{lap['potenza_media_w']}W" if lap.get("potenza_media_w") else "-"
                lines.append(f"| {lap_id} | {dist_l} | {vel} | {fc_m} | {fc_x} | {cad} | {pow_l} |")

    elif laps and act["sport"] == "swimming":
        lines.append("")
        lines.append("**ANALISI VASCHE:**")
        lines.append("| Vasca | Passo | FC Med | FC Max | SWOLF | Bracciate |")
        lines.append("|-------|-------|--------|--------|-------|-----------|")
        for lap in laps:
            lap_id = lap.get("lap_id", "?")
            passo = lap.get("passo_medio") or "-"
            fc_m = f"{lap['fc_media_bpm']}bpm" if lap.get("fc_media_bpm") else "-"
            fc_x = f"{lap['fc_max_bpm']}bpm" if lap.get("fc_max_bpm") else "-"
            swolf = str(lap.get("swolf") or "-")
            bracciate = str(lap.get("bracciate") or "-")
            lines.append(f"| {lap_id} | {passo} | {fc_m} | {fc_x} | {swolf} | {bracciate} |")

    lines.append("")
    return "\n".join(lines)

# -------------------------------------------------------------------------
# System instruction (profilo completo dell'atleta + persona del coach)
# -------------------------------------------------------------------------
def build_system_instruction() -> str:
    return (
        "Sei un Coach d'élite specializzato in Triathlon e Maratona, esperto nell'analisi di dati fisiologici "
        "e metriche avanzate Garmin. Sei empatico e motivante, ma estremamente schietto: ti basi sulla realtà "
        "dei fatti, correggendo dolcemente ma fermamente le convinzioni errate dell'atleta (es. recupero, "
        "idratazione, gestione sforzo). Non fingere emozioni umane, ma specchia l'entusiasmo e il tono "
        "informale dell'utente.\n\n"

        "## PROFILO COMPLETO DELL'ATLETA: DAVIDE MARIOTTI\n\n"

        "### STORIA E PROGRESSIONE\n"
        "- Davide parte da ZERO come runner (la settimana 2024_W36 rappresenta le sue PRIMISSIME uscite di corsa in assoluto).\n"
        "- Non trattarlo come un atleta esperto nelle settimane iniziali: il diario documenta la sua crescita da principiante.\n"
        "- **IMPORTANTE:** Davide ha acquistato la bici alla W16/2026. Prima di quella data, l'assenza di dati ciclismo è NORMALE e NON va mai commentata negativamente.\n"
        "- **IMPORTANTE:** Davide ha iniziato il corso di nuoto alla W18/2026. Prima di quella data, l'assenza di dati nuoto è NORMALE e NON va mai commentata negativamente.\n\n"

        "### TIMELINE GARE E OBIETTIVI\n"
        "1. 8 Dicembre 2024: Prima Mezza Maratona (senza preparazione specifica)\n"
        "2. Aprile 2025: Seconda Mezza Maratona (con preparazione strutturata)\n"
        "3. 30 Novembre 2025: Prima Maratona Completa (42 km)\n"
        "4. 29 Marzo 2026: Mezza Maratona\n"
        "5. 11 Ottobre 2026: Mezza Maratona\n"
        "6. 29 Novembre 2026: Maratona Completa — **OBIETTIVO PRINCIPALE: 3h30' (passo 4'58\"/km) con FC massima 150 bpm**\n"
        "7. 2 Maggio 2027: Ironman 70.3 (primo triathlon — primo obiettivo multisport)\n\n"

        "### OBIETTIVI ALLENAMENTO\n"
        "- Migliorare l'efficienza aerobica: ridurre la FC a parità di passo\n"
        "- Ritmi lenti più veloci, minore stress cardiaco in maratona\n"
        "- Migliore economia di corsa\n"
        "- Sviluppo base aerobica e controllo FC\n"
        "- Progressione graduale del volume\n"
        "- Lavori specifici di soglia e aumento VO2Max\n\n"

        "### PARAMETRI FISIOLOGICI\n"
        "- FC Max: 189 bpm\n"
        "- FC a Riposo: 44 bpm\n"
        "- rFTPw (Soglia Potenza Corsa): 344 Watt\n"
        "- FTP Bici: non ancora misurata formalmente\n\n"

        "### ZONE CARDIO PER SPORT\n"
        "**Corsa:**\n"
        "- Z1: 120-130 bpm | Z2: 131-150 bpm | Z3: 151-165 bpm | Z4: 166-180 bpm | Z5: >180 bpm\n\n"
        "**Bici:**\n"
        "- Z1: 112-122 bpm | Z2: 123-142 bpm | Z3: 143-157 bpm | Z4: 158-172 bpm | Z5: >172 bpm\n\n"
        "**Nuoto:**\n"
        "- Z1: 105-115 bpm | Z2: 116-135 bpm | Z3: 136-150 bpm | Z4: 151-165 bpm | Z5: >165 bpm\n\n"

        "### BENCHMARK METRICHE BIOMECCANICHE (CORSA)\n"
        "- **TCS (Tempo Contatto Suolo):** <250ms = élite, 250-270ms = buono, >270ms = da migliorare\n"
        "- **Bilanciamento TCS:** ideale 50/50 — segnalare asimmetrie >1.5% come potenziale rischio infortuni\n"
        "- **Oscillazione Verticale:** <8.0cm = ottima, 8.0-9.0cm = buona, >9.0cm = elevata (energia sprecata)\n"
        "- **Rapporto Verticale:** <8.5% = eccellente, 8.5-10% = buono, >10% = da correggere\n"
        "- **Cadenza:** 175-185 spm = target élite\n\n"

        "### PIANO DI ALLENAMENTO (Metodo simil-FIRST)\n"
        "- 3 corse (Qualità / Medio / Lungo)\n"
        "- 2 nuoti\n"
        "- 1-2 uscite in bici\n"
        "- Approccio multidisciplinare per ottimizzare il motore aerobico salvando le articolazioni\n\n"

        "### ATTREZZATURA\n"
        "- **Bici:** Wilier con prolunghe aerodinamiche (Profile Design Sonic/Ergo/35a) e sella da triathlon (ISM PN 3.0)\n"
        "- **Corsa (lunghi):** Gilet idrico da trail per 1-1.5L di liquidi\n\n"

        "### STRATEGIA NUTRIZIONALE\n"
        "- **Idratazione:** 1 grammo di sale ogni 500ml d'acqua; bere a piccoli sorsi continui (un sorso ogni km)\n"
        "- **Integrazione corsa:** 1 gel energetico (30-40g) ogni 7 km esatti\n"
        "- **Gel caffeina:** nell'ultimo terzo di gara/allenamento lungo\n\n"

        "### AREE DI ATTENZIONE PRIORITARIE\n"
        "- Deriva cardiaca (FC che sale a passo costante = fatica accumulata)\n"
        "- Rapporto passo/FC\n"
        "- Gestione dei ritmi nei lunghi\n"
        "- Corretta distribuzione dell'intensità settimanale\n\n"

        "## STILE DEI REPORT\n"
        "Tecnico, analitico e motivante. Analizza i volumi e le frequenze cardio citando ESPLICITAMENTE le zone "
        "(es. 'FC media 137 bpm = Zona 2 bassa — ottima base aerobica'). Usa Markdown con titoli e tabelle. "
        "Scrivi in italiano. Cita esplicitamente le settimane precedenti per tracciare trend (es. 'Rispetto a W20...'). "
        "Sii schietto ma costruttivo. Vai dritto al punto senza eccesso di formalismi."
    )

# -------------------------------------------------------------------------
# Costruzione prompt utente
# -------------------------------------------------------------------------
def build_user_prompt(week_id: str, year: int, week_num: int,
                      activities_text: str, history_text: str) -> str:
    today_str = date.today().strftime("%d/%m/%Y")
    past = is_past_week(year, week_num)

    future_section_note = (
        "\n\n**ISTRUZIONE IMPORTANTE:** La settimana analizzata è GIÀ PASSATA. "
        "NON includere la sezione '5. Indicazioni per la settimana successiva' — Davide ha già completato quelle sessioni. "
        "Fermati al giudizio complessivo."
        if past else
        "\n\n**ISTRUZIONE IMPORTANTE:** La settimana analizzata è ATTUALE o FUTURA. "
        "Includi obbligatoriamente la sezione '5. Indicazioni concrete per la settimana successiva'."
    )

    prompt = (
        f"DATA ODIERNA: {today_str}\n"
        f"SETTIMANA IN ANALISI: {week_id} (Anno {year}, Settimana ISO {week_num})\n"
        f"SETTIMANA PASSATA: {'SÌ' if past else 'NO'}\n"
        f"{future_section_note}\n\n"
        f"{'=' * 72}\n"
        f"STORICO REPORT PRECEDENTI (ultime settimane, per confronto):\n"
        f"{'=' * 72}\n"
        f"{history_text}\n\n"
        f"{'=' * 72}\n"
        f"DATI ALLENAMENTI SETTIMANA {week_id}:\n"
        f"{'=' * 72}\n"
        f"{activities_text}\n"
        f"{'=' * 72}\n\n"
        f"Redigi il report settimanale dell'allenatore in Markdown (italiano) con questa struttura ESATTA:\n\n"
        f"## 0. APERTURA DEL COACH\n"
        f"Commento personale e contestuale sulla settimana (tono diretto, non generico).\n\n"
        f"## 1. SINTESI VOLUME SETTIMANALE\n"
        f"Tabella con km, durata, FC media, sessioni per sport. Confronto % con settimana precedente.\n\n"
        f"## 2. ANALISI PER SPORT E PER SINGOLO ALLENAMENTO\n"
        f"Per ogni sport presente:\n"
        f"- Introduzione al blocco\n"
        f"Per ogni SINGOLA ATTIVITÀ:\n"
        f"- Giudizio individuale con dati specifici citati\n"
        f"- Analisi TCS (con benchmark e valutazione)\n"
        f"- Analisi Bilanciamento TCS (simmetria, asimmetrie rilevanti)\n"
        f"- Analisi Oscillazione Verticale e Rapporto Verticale (economia di corsa)\n"
        f"- Analisi Cadenza (rispetto del target 175-185 spm)\n"
        f"- Analisi FC: zone, deriva cardiaca (confronto primo/ultimo giro), picchi\n"
        f"- Per nuoto: SWOLF, bracciate, efficienza tecnica\n"
        f"- Per bici: potenza, W/kg, cadenza RPM\n\n"
        f"## 3. TREND E PROGRESSI / PUNTI CRITICI\n"
        f"Confronto esplicito con settimane precedenti (cita W reference). Identificare trend positivi e negativi.\n\n"
        f"## 4. GIUDIZIO COMPLESSIVO DEL COACH\n"
        f"Rating: ECCELLENTE / OTTIMA / BUONA / NELLA NORMA / DI SCARICO / INSUFFICIENTE / CRITICA\n"
        f"Motivazione sintetica del giudizio.\n"
        + (
            "" if past else
            "\n\n## 5. INDICAZIONI CONCRETE PER LA SETTIMANA SUCCESSIVA\n"
            "Prescrizioni specifiche con target di FC, passo, volume per ogni sessione.\n"
        )
    )
    return prompt

# -------------------------------------------------------------------------
# Chiamata all'API Gemini
# -------------------------------------------------------------------------
def call_gemini_api(api_key: str, system_instruction: str, user_prompt: str,
                    model_name: str = "gemini-2.5-pro"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [
            {
                "parts": [{"text": user_prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.3,
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    retries = 5
    backoff = 3
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

                candidates = res_json.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text"), res_json.get("usageMetadata", {})

                raise Exception(f"Risposta API non valida: {res_body[:500]}")

        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8") if e.fp else ""
            print(f"  [HTTP ERROR {e.code}] {e.reason}")

            if e.code == 429 and attempt < retries - 1:
                retry_seconds = 30.0
                try:
                    err_json = json.loads(err_content)
                    details = err_json.get("error", {}).get("details", [])
                    for detail in details:
                        if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                            delay_str = detail.get("retryDelay", "")
                            m = re.search(r"([\d\.]+)", delay_str)
                            if m:
                                retry_seconds = float(m.group(1)) + 2.0
                                break
                except Exception:
                    pass
                print(f"  [RATE LIMIT] Attendo {retry_seconds:.1f} secondi...")
                time.sleep(retry_seconds)
                continue

            if err_content:
                print(f"  Dettaglio: {err_content[:500]}")
            raise e

        except Exception as e:
            print(f"  [ERRORE DI RETE] {e}")
            if attempt < retries - 1:
                print(f"  Riprovo tra {backoff} secondi...")
                time.sleep(backoff)
                backoff *= 2
                continue
            raise e

    return None, {}

# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------
def main():
    print("\n" + "=" * 60)
    print("DIARIO DELL'ALLENATORE AI — GENERATORE REPORT SETTIMANALI")
    print("=" * 60)

    # 1. Carica configurazione
    env = load_env()
    api_key = env.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key in ("tuo_api_key_qui", ""):
        print("[ERRORE] Chiave API Gemini non trovata.")
        print("Crea un file chiamato `.env` nella root del progetto e aggiungi:")
        print("GEMINI_API_KEY=la_tua_chiave_api_qui")
        return

    model_name = (
        env.get("GEMINI_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or "gemini-2.5-pro"
    )
    print(f"[INFO] Modello: {model_name}")

    DIARY_DIR.mkdir(exist_ok=True)

    # 2. Scansione cartelle output
    base_dir = Path(__file__).parent
    output_dirs = sorted([
        d for d in base_dir.iterdir()
        if d.is_dir() and re.match(r"^output\d{4}$", d.name)
    ])

    if not output_dirs:
        print("[ERRORE] Nessuna cartella 'output<ANNO>' trovata.")
        return

    weeks_to_process = []
    for d in output_dirs:
        year = d.name.replace("output", "")
        for w_dir in sorted(d.iterdir()):
            if w_dir.is_dir() and re.match(r"^W\d+$", w_dir.name):
                week_num = int(w_dir.name[1:])
                weeks_to_process.append({
                    "year": year,
                    "year_int": int(year),
                    "week_name": w_dir.name,
                    "week_num": week_num,
                    "path": w_dir,
                })

    weeks_to_process.sort(key=lambda x: (x["year_int"], x["week_num"]))
    print(f"[INFO] Trovate {len(weeks_to_process)} settimane convertite.")

    # 3. Carica report esistenti
    previous_reports = []
    for wk in weeks_to_process:
        report_file = DIARY_DIR / f"{wk['year']}_{wk['week_name']}_report.md"
        if report_file.exists():
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    content = f.read()
                previous_reports.append({
                    "week_id": f"{wk['year']}_{wk['week_name']}",
                    "content": content,
                })
            except Exception as e:
                print(f"  [ERRORE] Lettura report {report_file.name}: {e}")

    print(f"[INFO] Caricati {len(previous_reports)} report esistenti come storico.")

    # 4. Gestione modalità settimana singola
    target_year = env.get("TARGET_YEAR") or os.environ.get("TARGET_YEAR")
    target_week = env.get("TARGET_WEEK") or os.environ.get("TARGET_WEEK")

    is_test_mode = False
    if target_year and target_week:
        target_year = target_year.strip()
        target_week = target_week.strip().upper()

        target_wk = None
        target_idx = -1
        for idx, wk in enumerate(weeks_to_process):
            if wk["year"] == target_year and wk["week_name"] == target_week:
                target_wk = wk
                target_idx = idx
                break

        if target_wk is None:
            print(f"[ERRORE] Settimana {target_year}_{target_week} non trovata.")
            return

        print(f"[INFO] Modalità settimana singola: {target_year}_{target_week}")

        prev_ids = {f"{w['year']}_{w['week_name']}" for w in weeks_to_process[:target_idx]}
        previous_reports = [r for r in previous_reports if r["week_id"] in prev_ids]
        print(f"[INFO] Storico filtrato: {len(previous_reports)} report precedenti.")

        weeks_to_process = [target_wk]
        is_test_mode = True

    # 5. Prepara system instruction (fissa per tutte le settimane)
    system_instruction = build_system_instruction()

    # 6. Elaborazione progressiva
    processed_count = 0

    for wk in weeks_to_process:
        week_id = f"{wk['year']}_{wk['week_name']}"
        report_file = DIARY_DIR / f"{week_id}_report.md"

        if report_file.exists() and not is_test_mode:
            continue

        print(f"\n--- Generazione Report per {week_id} ---")

        # Leggi le attività della settimana
        json_files = sorted(list(wk["path"].glob("*.json")))
        if not json_files:
            print(f"  [WARNING] Nessun file JSON in {wk['path'].name}, salto.")
            continue

        activities_text = ""
        for jf in json_files:
            act = parse_activity_json(jf)
            if act:
                activities_text += build_activity_prompt_text(act) + "\n"

        if not activities_text.strip():
            print(f"  [WARNING] Nessuna attività valida per {week_id}, salto.")
            continue

        # Storico ultimi 15 report
        recent_history = previous_reports[-15:]
        if recent_history:
            history_text = ""
            for r in recent_history:
                history_text += (
                    f"\n--- INIZIO REPORT {r['week_id']} ---\n"
                    f"{r['content']}\n"
                    f"--- FINE REPORT {r['week_id']} ---\n"
                )
        else:
            history_text = "Nessun report precedente disponibile. Questo è il primo report del diario.\n"

        # Costruisci prompt
        user_prompt = build_user_prompt(
            week_id=week_id,
            year=wk["year_int"],
            week_num=wk["week_num"],
            activities_text=activities_text,
            history_text=history_text,
        )

        print(f"  Invio richiesta a Gemini ({model_name})...")
        try:
            report_content, usage = call_gemini_api(
                api_key, system_instruction, user_prompt, model_name=model_name
            )
            if report_content:
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(report_content)
                print(f"  [OK] Report salvato: {report_file}")

                p_tokens = usage.get("promptTokenCount", 0)
                c_tokens = usage.get("candidatesTokenCount", 0)
                t_tokens = usage.get("totalTokenCount", 0)
                print(f"  [STATS] Token — Input: {p_tokens} | Output: {c_tokens} | Totale: {t_tokens}")

                previous_reports.append({
                    "week_id": week_id,
                    "content": report_content,
                })
                processed_count += 1

                # Pausa per evitare rate limit (2.5 Pro ha limiti RPM bassi)
                if not is_test_mode:
                    time.sleep(5)
            else:
                print("  [ERRORE] Nessun contenuto generato dall'API.")

        except Exception as e:
            print(f"  [ERRORE CRITICO] Settimana {week_id}: {e}")
            print("  Interruzione. Risolvi il problema prima di riavviare.")
            break

    print("\n" + "=" * 60)
    print(f"COMPLETATO. Generati {processed_count} nuovi report.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
