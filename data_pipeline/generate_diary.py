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
import argparse
import firebase_admin
from firebase_admin import credentials, firestore

# --- Configurazione ---
ROOT_DIR = Path(__file__).parent.parent
DIARY_DIR = ROOT_DIR / "frontend" / "diary"
# -------------------------------------------------------------------------
# Caricamento .env
# -------------------------------------------------------------------------
def load_env():
    env_path = ROOT_DIR / ".env"
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
def build_activity_prompt_text(act, max_hr=190):
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

    # Indice di Intensità Cardiaca (rapporto FC media / FC Max atleta)
    if fc_med and isinstance(fc_med, (int, float)) and fc_med > 0 and max_hr:
        hr_intensity = (fc_med / max_hr) * 100
        if hr_intensity >= 92:
            intensity_label = "SFORZO MASSIMALE — l'atleta ha dato tutto"
        elif hr_intensity >= 85:
            intensity_label = "SFORZO ELEVATO — forte ma con margine residuo"
        elif hr_intensity >= 78:
            intensity_label = "SFORZO MODERATO/CONSERVATIVO — gara gestita con prudenza"
        elif hr_intensity >= 70:
            intensity_label = "SFORZO CONSERVATIVO — nessuna spinta al limite"
        else:
            intensity_label = "SFORZO LEGGERO — ritmo controllato"
        lines.append(f"- **Indice Intensità Cardiaca:** {hr_intensity:.1f}% della FC Max ({fc_med}/{max_hr} bpm) → {intensity_label}")

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
def build_system_instruction(profile: dict) -> str:
    name = profile.get("name", "Atleta")
    max_hr = profile.get("max_hr", "N/A")
    resting_hr = profile.get("resting_hr", "N/A")
    lthr = profile.get("lthr", "N/A")
    z1 = profile.get("z1_bottom", "N/A")
    z2 = profile.get("z2_bottom", "N/A")
    z3 = profile.get("z3_bottom", "N/A")
    z4 = profile.get("z4_bottom", "N/A")
    z5 = profile.get("z5_bottom", "N/A")
    z2_ceiling = profile.get("z2_ceiling", "N/A")

    if name == "athlete_main" or "Davide" in str(name):
        name_display = "DAVIDE MARIOTTI"
        storia = (
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
            "- Lavori specifici di soglia e aumento VO2Max\n"
        )
    else:
        name_display = str(name).upper()
        storia = (
            "### STORIA E PROGRESSIONE\n"
            "- Atleta in monitoraggio. Adatta i commenti ai ritmi e alla FC letta dai dati.\n\n"
            "### OBIETTIVI ALLENAMENTO\n"
            "- Migliorare l'efficienza aerobica e la gestione degli sforzi.\n"
            "- Sviluppo base aerobica e controllo FC.\n"
        )

    return (
        f"Sei un Coach d'élite specializzato in Triathlon e Maratona, esperto nell'analisi di dati fisiologici "
        f"e metriche avanzate Garmin. Sei empatico e motivante, ma estremamente schietto: ti basi sulla realtà "
        f"dei fatti, correggendo dolcemente ma fermamente le convinzioni errate dell'atleta. Non fingere emozioni "
        f"umane, ma specchia l'entusiasmo e il tono informale dell'utente.\n\n"
        f"## PROFILO COMPLETO DELL'ATLETA: {name_display}\n\n"
        f"{storia}\n"
        f"### PARAMETRI FISIOLOGICI\n"
        f"- FC Max: {max_hr} bpm\n"
        f"- FC a Riposo: {resting_hr} bpm\n"
        f"- Soglia (LTHR): {lthr} bpm\n\n"
        f"### ZONE CARDIO PER SPORT (CORSA)\n"
        f"- Z1 (Recupero): {z1}+ bpm\n"
        f"- Z2 (Fondo Lento): {z2} - {z2_ceiling} bpm\n"
        f"- Z3 (Fondo Medio): {z3}+ bpm\n"
        f"- Z4 (Soglia): {z4}+ bpm\n"
        f"- Z5 (VO2Max): {z5}+ bpm\n\n"
        "### BENCHMARK METRICHE BIOMECCANICHE (CORSA)\n"
        "- **TCS (Tempo Contatto Suolo):** <250ms = élite, 250-270ms = buono, >270ms = da migliorare\n"
        "- **Bilanciamento TCS:** ideale 50/50 — segnalare asimmetrie >1.5% come potenziale rischio infortuni\n"
        "- **Oscillazione Verticale:** <8.0cm = ottima, 8.0-9.0cm = buona, >9.0cm = elevata (energia sprecata)\n"
        "- **Rapporto Verticale:** <8.5% = eccellente, 8.5-10% = buono, >10% = da correggere\n"
        "- **Cadenza:** 175-185 spm = target élite\n\n"
        "### STRATEGIA NUTRIZIONALE\n"
        "- **Idratazione:** 1 grammo di sale ogni 500ml d'acqua; bere a piccoli sorsi continui (un sorso ogni km)\n"
        "- **Integrazione corsa:** 1 gel energetico (30-40g) ogni 7 km esatti\n"
        "- **Gel caffeina:** nell'ultimo terzo di gara/allenamento lungo\n\n"
        "### AREE DI ATTENZIONE PRIORITARIE\n"
        "- Deriva cardiaca (FC che sale a passo costante = fatica accumulata)\n"
        "- Rapporto passo/FC\n"
        "- Gestione dei ritmi nei lunghi\n"
        "- Corretta distribuzione dell'intensità settimanale\n\n"

        "### ANALISI INTENSITÀ CARDIACA IN GARA E IN ALLENAMENTO\n"
        "- L'Indice di Intensità Cardiaca (FC media / FC Max atleta × 100) indica quanta riserva cardiaca è stata usata.\n"
        "- ≥92%: Sforzo massimale, l'atleta ha dato tutto. Riconoscerlo esplicitamente.\n"
        "- 85-91%: Sforzo elevato ma con margine. L'atleta ha corso forte ma non al limite.\n"
        "- 78-84%: Sforzo moderato/conservativo. L'atleta ha gestito la gara prudentemente, NON ha dato il massimo.\n"
        "- <78%: Sforzo leggero, molto conservativo.\n"
        "- NON assumere MAI che in una gara l'atleta abbia dato il massimo. DEVI verificarlo con l'Indice di Intensità.\n"
        "- In una mezza maratona: ≥90% è sforzo totale, 80-89% è gestione strategica, <80% è conservativo.\n"
        "- ESEMPIO: FC media 175 bpm su FC Max 189 → 92.6% = ha dato tutto. "
        "FC media 159 bpm su FC Max 189 → 84.1% = gara gestita con prudenza, non ha spinto al massimo.\n\n"

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

    prompt = (
        f"DATA ODIERNA: {today_str}\n"
        f"SETTIMANA IN ANALISI: {week_id} (Anno {year}, Settimana ISO {week_num})\n"
        f"\n**ISTRUZIONE IMPORTANTE:** NON includere MAI indicazioni per la settimana successiva. Fermati al giudizio complessivo.\n\n"
        f"{'=' * 72}\n"
        f"STORICO REPORT PRECEDENTI (ultime settimane, per confronto):\n"
        f"{'=' * 72}\n"
        f"{history_text}\n\n"
        f"{'=' * 72}\n"
        f"DATI ALLENAMENTI SETTIMANA {week_id}:\n"
        f"{'=' * 72}\n"
        f"{activities_text}\n"
        f"{'=' * 72}\n\n"
        f"## REGOLE DI STILE OBBLIGATORIE PER EVITARE RIPETITIVITÀ\n"
        f"- L'apertura del coach (sezione 0) DEVE iniziare ogni settimana con un incipit COMPLETAMENTE diverso. "
        f"MAI usare 'Davide, mettiamoci a sedere' o strutture simili ripetute. "
        f"Varia radicalmente: usa metafore nuove, riferimenti al meteo/stagione, aneddoti legati ai dati, "
        f"domande provocatorie, citazioni sportive, flashback su progressi specifici.\n"
        f"- Le espressioni 'fai un bel respiro', 'guardami negli occhi', 'mettiti comodo', "
        f"'apro il tuo diario', 'togliti le scarpe' sono VIETATE perché già abusate nei report precedenti.\n"
        f"- Usa aggettivi, metafore e strutture sintattiche diverse da quelle dei report precedenti forniti come storico.\n"
        f"- Per le analisi FC, varia il modo di esprimere i giudizi: usa analogie diverse, "
        f"cambia il livello di dettaglio, a volte sii sintetico e diretto, altre volte narrativo.\n"
        f"- Per il giudizio finale, NON usare sempre la stessa struttura 'Ti do X e non Y per un solo motivo:'. Cambia formato.\n"
        f"- Leggi attentamente i report precedenti forniti e EVITA DELIBERATAMENTE di ricalcarne frasi, strutture e ritornelli.\n"
        f"- Quando presenti l'Indice di Intensità Cardiaca per un'attività di gara, analizza se l'atleta "
        f"ha dato il massimo o ha gestito lo sforzo con prudenza. Non dare mai per scontato che in gara si dia tutto.\n\n"
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
        f"- Analisi Indice di Intensità Cardiaca: in gara e allenamenti intensi, valuta la % di FC Max usata\n"
        f"- Per nuoto: SWOLF, bracciate, efficienza tecnica\n"
        f"- Per bici: potenza, W/kg, cadenza RPM\n\n"
        f"## 3. TREND E PROGRESSI / PUNTI CRITICI\n"
        f"Confronto esplicito con settimane precedenti (cita W reference). Identificare trend positivi e negativi.\n\n"
        f"## 4. GIUDIZIO COMPLESSIVO DEL COACH\n"
        f"Rating: ECCELLENTE / OTTIMA / BUONA / NELLA NORMA / DI SCARICO / INSUFFICIENTE / CRITICA\n"
        f"Motivazione sintetica del giudizio.\n"
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
            "temperature": 0.75,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--user_id", type=str, default="athlete_main", help="ID Utente")
    args = parser.parse_args()
    user_id = args.user_id

    print("\n" + "=" * 60)
    print(f"DIARIO DELL'ALLENATORE AI — GENERATORE REPORT ({user_id})")
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
    
    # 1.b Inizializza Firebase
    sa_path = ROOT_DIR / "service-account.json"
    if sa_path.exists():
        cred = credentials.Certificate(str(sa_path))
    else:
        cred = credentials.ApplicationDefault()
        
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {'projectId': 'running-data-445817'})
    db = firestore.client()
    
    # 1.c Carica Profilo
    profile_doc = db.collection("athletes").document(user_id).get()
    profile = profile_doc.to_dict() if profile_doc.exists else {"name": user_id}
    max_hr = profile.get("max_hr", 190)

    # 2. Scansione cartelle output
    data_dir = ROOT_DIR / "data"
    output_dirs = sorted([
        d for d in data_dir.iterdir()
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

    # 3. Carica report esistenti (dalla struttura diary/{anno}/)
    previous_reports = []
    for wk in weeks_to_process:
        year_dir = DIARY_DIR / wk['year']
        report_file = year_dir / f"{wk['year']}_{wk['week_name']}_report.md"
        # Fallback: cerca anche nella root di diary/ per retrocompatibilità
        if not report_file.exists():
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
    system_instruction = build_system_instruction(profile)

    # 6. Elaborazione progressiva
    processed_count = 0

    for wk in weeks_to_process:
        week_id = f"{wk['year']}_{wk['week_name']}"
        year_dir = DIARY_DIR / wk['year']
        year_dir.mkdir(parents=True, exist_ok=True)
        report_file = year_dir / f"{week_id}_{user_id}_report.md"

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
                activities_text += build_activity_prompt_text(act, max_hr=max_hr) + "\n"

        if not activities_text.strip():
            print(f"  [WARNING] Nessuna attività valida per {week_id}, salto.")
            continue

        # Storico ultimi 12 report
        recent_history = previous_reports[-12:]
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
                print(f"  [OK] Report salvato localmente: {report_file}")
                
                # Salva su Firestore per lettura multi-utente
                try:
                    db.collection(f"athletes/{user_id}/diaries").document(week_id).set({
                        "week_id": week_id,
                        "content": report_content,
                        "updated_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
                    print(f"  [OK] Report salvato su Firestore per l'utente {user_id}")
                except Exception as db_err:
                    print(f"  [ERRORE] Salvataggio su Firestore fallito: {db_err}")

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
