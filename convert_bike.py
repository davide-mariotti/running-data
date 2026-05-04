#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Bike Activity Converter - Converte le uscite in bici in JSON
====================================================================
UTILIZZO:
  1. Metti i file CSV e GPX delle attività bici nella cartella:
       bike/activity_<ID>.csv  e  activity_<ID>.gpx
  2. Lancia lo script dalla root del progetto con:
       python convert_bike.py
  3. Troverai i file di output in: output/bike/
     - Un JSON per ogni attività: bike_activity_<ID>.json
     - Un JSON aggregato con tutte le uscite: all_bike.json

REQUISITI:
  - Python 3.8+
  - I file CSV e GPX devono essere nella cartella:  bike/
"""

# ── CONFIGURAZIONE ─────────────────────────────────────────────────────────────
# Cartella sorgente contenente i file CSV e GPX delle attività bici
BIKE_DIR = "bike"
# ───────────────────────────────────────────────────────────────────────────────

import io, sys
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


# ── Mapping colonne CSV bici -> chiavi JSON snake_case ────────────────────────
# Colonne comuni a tutte le attività
CSV_KEY_MAP = {
    "Lap":                              "lap",
    "Tempo":                            "tempo",
    "Tempo cumulato":                   "tempo_cumulato",
    "Distanza":                         "distanza_km",      # bici: senza "km" nell'intestazione
    "Distanza km":                      "distanza_km",      # fallback corsa
    "Velocità media":                   "velocita_media_kmh",
    "Velocità max":                     "velocita_max_kmh",
    "Velocità media in movimento":      "velocita_media_movimento_kmh",
    "FC Media":                         "fc_media_bpm",
    "FC Media bpm":                     "fc_media_bpm",     # fallback corsa
    "FC max":                           "fc_max_bpm",
    "FC max bpm":                       "fc_max_bpm",       # fallback corsa
    "Ascesa totale":                    "ascesa_m",
    "Ascesa totale m":                  "ascesa_m",         # fallback corsa
    "Discesa totale":                   "discesa_m",
    "Discesa totale m":                 "discesa_m",        # fallback corsa
    "Cadenza pedalata media":           "cadenza_pedalata_media_rpm",
    "Cadenza pedalata max":             "cadenza_pedalata_max_rpm",
    "Calorie":                          "calorie",
    "Calorie C":                        "calorie",          # fallback corsa
    "Tempo in movimento":               "tempo_in_movimento",
    "Potenza media W":                  "potenza_media_w",
    "Potenza max W":                    "potenza_max_w",
    "W/kg medio":                       "wkg_medio",
    "W/kg massimo":                     "wkg_massimo",
    "Temperatura med":                  "temperatura_med",
}


def normalize_key(k: str) -> str:
    """Converte l'intestazione CSV in chiave JSON snake_case."""
    mapped = CSV_KEY_MAP.get(k.strip())
    if mapped:
        return mapped
    # Fallback: normalizzazione automatica
    s = unicodedata.normalize("NFKD", k.strip()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def clean_value(v: str):
    """Converte il valore CSV nel tipo Python più appropriato."""
    v = v.strip()
    if v in ("--", "", "N/D"):
        return None
    # Rimuove il separatore delle migliaia (virgola) prima di parsare
    v_clean = v.replace(",", "")
    try:
        return int(v_clean)
    except ValueError:
        pass
    try:
        return float(v_clean)
    except ValueError:
        pass
    return v


# ── Parser CSV ─────────────────────────────────────────────────────────────────
def parse_csv(csv_path: Path) -> dict:
    """Legge il CSV Garmin e restituisce laps e summary come dict."""
    laps, summary = [], None
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lap_label = row.get("Lap", "").strip()
            record = {normalize_key(k): clean_value(v) for k, v in row.items()}
            if lap_label == "Riepilogo":
                summary = record
            else:
                laps.append(record)
    return {"laps": laps, "summary": summary}


# ── Parser GPX (solo metadati) ─────────────────────────────────────────────────
def parse_gpx_meta(gpx_path: Path) -> dict:
    """Estrae name, date, start_time e type dal file GPX."""
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    tag = root.tag
    ns_url = tag.split("}")[0].lstrip("{") if "}" in tag else "http://www.topografix.com/GPX/1/1"

    meta_time_el = root.find(f"{{{ns_url}}}metadata/{{{ns_url}}}time")
    start_time_utc = meta_time_el.text if meta_time_el is not None else None

    trk = root.find(f"{{{ns_url}}}trk")
    name_el = trk.find(f"{{{ns_url}}}name") if trk is not None else None
    type_el = trk.find(f"{{{ns_url}}}type") if trk is not None else None

    date, start_time = None, None
    if start_time_utc:
        m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", start_time_utc)
        if m:
            date, start_time = m.group(1), m.group(2)

    return {
        "name":            name_el.text.strip() if name_el is not None and name_el.text else None,
        "date":            date,
        "start_time_utc":  start_time_utc,
        "start_time":      start_time,
        "type":            type_el.text.strip() if type_el is not None and type_el.text else None,
    }


# ── Elaborazione attività ──────────────────────────────────────────────────────
def process_bike_dir(bike_dir: Path) -> list:
    """Processa tutte le coppie CSV+GPX nella cartella bike e restituisce la lista delle attività."""
    files_by_id = defaultdict(dict)
    for f in bike_dir.iterdir():
        if not f.is_file():
            continue
        m = re.match(r"activity_(\d+)\.(csv|gpx)", f.name, re.IGNORECASE)
        if m:
            files_by_id[m.group(1)][m.group(2).lower()] = f

    activities = []
    for aid in sorted(files_by_id):
        fmap = files_by_id[aid]
        if "csv" not in fmap:
            print(f"  ! {aid}: CSV mancante, skip")
            continue
        if "gpx" not in fmap:
            print(f"  ! {aid}: GPX mancante, skip")
            continue

        print(f"  -> activity {aid}")
        meta     = parse_gpx_meta(fmap["gpx"])
        csv_data = parse_csv(fmap["csv"])

        activities.append({
            "activity_id":    aid,
            "sport":          "cycling",
            "name":           meta["name"],
            "date":           meta["date"],
            "start_time_utc": meta["start_time_utc"],
            "start_time":     meta["start_time"],
            "type":           meta["type"],
            "laps":           csv_data["laps"],
            "summary":        csv_data["summary"],
        })

    return activities


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    bike_dir   = Path(__file__).parent / BIKE_DIR
    output_dir = Path(__file__).parent / "output" / "bike"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bike_dir.is_dir():
        print(f"[ERRORE] Cartella bici non trovata: {bike_dir}")
        sys.exit(1)

    print(f"\n[START] Processo le attività bici da: {bike_dir}")
    print(f"        Output -> {output_dir}\n")

    activities = process_bike_dir(bike_dir)

    if not activities:
        print(f"[!] Nessuna attività trovata in {bike_dir}.")
        sys.exit(1)

    # ── Un JSON per ogni attività ────────────────────────────────────────────
    for act in activities:
        aid      = act["activity_id"]
        out_file = output_dir / f"bike_activity_{aid}.json"
        with open(out_file, "w", encoding="utf-8") as out:
            json.dump(act, out, ensure_ascii=False, indent=2)
        print(f"     ✓  {out_file.name}")

    # ── JSON aggregato con tutte le uscite (ordinato per data) ───────────────
    activities_sorted = sorted(
        activities,
        key=lambda a: (a["date"] or "", a["start_time_utc"] or "")
    )

    all_bike = {
        "sport":            "cycling",
        "activity_count":   len(activities_sorted),
        "activities":       activities_sorted,
    }

    all_file = output_dir / "all_bike.json"
    with open(all_file, "w", encoding="utf-8") as out:
        json.dump(all_bike, out, ensure_ascii=False, indent=2)

    print(f"\n[OK] {len(activities)} attività -> {output_dir}")
    print(f"     Aggregato: {all_file.name}")


if __name__ == "__main__":
    main()
