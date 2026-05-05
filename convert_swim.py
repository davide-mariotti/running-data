#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Swim Activity Converter - Converte le uscite di nuoto in JSON
====================================================================
UTILIZZO:
  1. Metti i file CSV e GPX delle attività di nuoto nella cartella:
       swim/activity_<ID>.csv  e  activity_<ID>.gpx
  2. Lancia lo script dalla root del progetto con:
       python convert_swim.py
  3. Troverai i file di output in: output/swim/
     - Un JSON per ogni attività: swim_activity_<ID>.json
     - Un JSON aggregato con tutte le uscite: all_swim.json

REQUISITI:
  - Python 3.8+
  - I file CSV e GPX devono essere nella cartella:  swim/
"""

# ── CONFIGURAZIONE ─────────────────────────────────────────────────────────────
# Cartella sorgente contenente i file CSV e GPX delle attività di nuoto
SWIM_DIR = "swim"
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


# ── Mapping colonne CSV nuoto -> chiavi JSON snake_case ────────────────────────
# Colonne specifiche per il nuoto
CSV_KEY_MAP = {
    "Ripetute":                         "lap",
    "Stile":                            "stile",
    "Vasche":                           "vasche",
    "Distanza":                         "distanza_m",
    "Tempo":                            "tempo",
    "Tempo cumulato":                   "tempo_cumulato",
    "Passo medio":                      "passo_medio",
    "Passo migliore":                   "passo_migliore",
    "Swolf medio":                      "swolf_medio",
    "FC Media":                         "fc_media_bpm",
    "FC max":                           "fc_max_bpm",
    "Totale bracciate":                 "totale_bracciate",
    "Bracciate medie":                  "bracciate_medie",
    "Calorie":                          "calorie",
}


def normalize_key(k: str) -> str:
    """Converte l'intestazione CSV in chiave JSON snake_case."""
    if not k:
        return None
    mapped = CSV_KEY_MAP.get(k.strip())
    if mapped:
        return mapped
    # Fallback: normalizzazione automatica
    s = unicodedata.normalize("NFKD", k.strip()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def clean_value(v: str):
    """Converte il valore CSV nel tipo Python più appropriato."""
    if v is None:
        return None
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
            lap_label = row.get("Ripetute", "").strip()
            record = {}
            for k, v in row.items():
                norm_k = normalize_key(k)
                if norm_k:
                    record[norm_k] = clean_value(v)
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
def process_swim_dir(swim_dir: Path, output_dir: Path) -> list:
    """Processa tutte le coppie CSV+GPX nella cartella swim e restituisce la lista delle attività (legge da cache se già processate)."""
    files_by_id = defaultdict(dict)
    for f in swim_dir.iterdir():
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

        out_file = output_dir / f"swim_activity_{aid}.json"
        if out_file.exists():
            print(f"  -> activity {aid} (già processata, leggo da cache)")
            with open(out_file, "r", encoding="utf-8") as f:
                cached_act = json.load(f)
                cached_act["_cached"] = True
                activities.append(cached_act)
            continue

        print(f"  -> activity {aid}")
        meta     = parse_gpx_meta(fmap["gpx"])
        csv_data = parse_csv(fmap["csv"])

        activities.append({
            "activity_id":    aid,
            "sport":          "swimming",
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
    swim_dir   = Path(__file__).parent / SWIM_DIR
    output_dir = Path(__file__).parent / "output" / "swim"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not swim_dir.is_dir():
        print(f"[ERRORE] Cartella nuoto non trovata: {swim_dir}")
        sys.exit(1)

    print(f"\n[START] Processo le attività di nuoto da: {swim_dir}")
    print(f"        Output -> {output_dir}\n")

    activities = process_swim_dir(swim_dir, output_dir)

    if not activities:
        print(f"[!] Nessuna attività trovata in {swim_dir}.")
        sys.exit(1)

    # ── Un JSON per ogni attività ────────────────────────────────────────────
    for act in activities:
        if act.pop("_cached", False):
            continue
        aid      = act["activity_id"]
        out_file = output_dir / f"swim_activity_{aid}.json"
        with open(out_file, "w", encoding="utf-8") as out:
            json.dump(act, out, ensure_ascii=False, indent=2)
        print(f"     ✓  {out_file.name}")

    # ── JSON aggregato con tutte le uscite (ordinato per data) ───────────────
    activities_sorted = sorted(
        activities,
        key=lambda a: (a["date"] or "", a["start_time_utc"] or "")
    )

    all_swim = {
        "sport":            "swimming",
        "activity_count":   len(activities_sorted),
        "activities":       activities_sorted,
    }

    all_file = output_dir / "all_swim.json"
    with open(all_file, "w", encoding="utf-8") as out:
        json.dump(all_swim, out, ensure_ascii=False, indent=2)

    print(f"\n[OK] {len(activities)} attività -> {output_dir}")
    print(f"     Aggregato: {all_file.name}")


if __name__ == "__main__":
    main()
