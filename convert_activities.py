#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Activity Converter - Genera un JSON per ogni allenamento di una settimana
============================================================
UTILIZZO:
  1. Imposta la variabile WEEK_NAME qui sotto con la settimana che vuoi processare
     (es. "W04", "W12", ecc.)
  2. Lancia lo script dalla root del progetto con:
       python convert_activities.py
  3. Troverai i file di output in: output/<WEEK_NAME>/
     Un file JSON per ogni allenamento, nominato:
       <WEEK_NAME>_activity_<ID>.json
     Esempio per W04 con 4 allenamenti:
       output/W04/W04_activity_22609161973.json
       output/W04/W04_activity_22622465339.json
       ...

REQUISITI:
  - Python 3.8+
  - I file CSV e GPX delle attivita devono essere nella cartella:
    2026-10-29-M/<WEEK_NAME>/activity_<ID>.csv  e  activity_<ID>.gpx
"""

# ── CONFIGURAZIONE ─────────────────────────────────────────────────────────────
# Modifica questa variabile per scegliere la settimana da processare
WEEK_NAME = "W05"
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


# ── Mapping colonne CSV -> chiavi JSON snake_case ──────────────────────────────
CSV_KEY_MAP = {
    "Lap":                                                 "lap",
    "Tempo":                                               "tempo",
    "Tempo cumulato":                                      "tempo_cumulato",
    "Distanza km":                                         "distanza_km",
    "Passo medio min/km":                                  "passo_medio",
    "PRP medio min/km":                                    "prp_medio",
    "FC Media bpm":                                        "fc_media_bpm",
    "FC max bpm":                                          "fc_max_bpm",
    "Ascesa totale m":                                     "ascesa_m",
    "Discesa totale m":                                    "discesa_m",
    "Potenza media W":                                     "potenza_media_w",
    "W/kg medio":                                          "wkg_medio",
    "Potenza max W":                                       "potenza_max_w",
    "W/kg massimo":                                        "wkg_massimo",
    "Cadenza di corsa media pam":                          "cadenza_media_pam",
    "Tempo medio di contatto con il suolo ms":             "contatto_suolo_ms",
    "Media bilanciamento TCS %":                           "bilanciamento_tcs",
    "Lunghezza media passo m":                             "lunghezza_passo_m",
    "Oscillazione verticale media cm":                     "oscillazione_verticale_cm",
    "Rapporto verticale medio %":                          "rapporto_verticale_pct",
    "Calorie C":                                           "calorie",
    "Temperatura med":                                     "temperatura_med",
    "Passo migliore min/km":                               "passo_migliore",
    "Cadenza di corsa max pam":                            "cadenza_max_pam",
    "Tempo in movimento":                                  "tempo_in_movimento",
    "Passo medio in movimento min/km":                     "passo_medio_in_movimento",
    "Perdita velocità di passo media cm/s":                "perdita_velocita_cms",
    "Percentuale perdita velocità di passo media %":       "perdita_velocita_pct",
}

def normalize_key(k: str) -> str:
    mapped = CSV_KEY_MAP.get(k.strip())
    if mapped:
        return mapped
    s = unicodedata.normalize("NFKD", k.strip()).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def clean_value(v: str):
    v = v.strip()
    if v in ("--", "", "N/D"):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v.replace(",", ""))
    except ValueError:
        pass
    return v


# ── Parser CSV ─────────────────────────────────────────────────────────────────
def parse_csv(csv_path: Path) -> dict:
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


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    base_dir   = Path(__file__).parent / "2026-10-29-M"
    output_dir = Path(__file__).parent / "output" / WEEK_NAME
    output_dir.mkdir(parents=True, exist_ok=True)

    week_dir = base_dir / WEEK_NAME
    if not week_dir.is_dir():
        print(f"[ERRORE] Cartella settimana non trovata: {week_dir}")
        sys.exit(1)

    print(f"\n[START] Processo gli allenamenti di: {WEEK_NAME}")
    print(f"        Output -> {output_dir}\n")

    # Raggruppa i file CSV/GPX per activity ID
    files_by_id = defaultdict(dict)
    for f in week_dir.iterdir():
        if not f.is_file():
            continue
        m = re.match(r"activity_(\d+)\.(csv|gpx)", f.name, re.IGNORECASE)
        if m:
            files_by_id[m.group(1)][m.group(2).lower()] = f

    if not files_by_id:
        print(f"[!] Nessun file activity_*.csv/gpx trovato in {week_dir}")
        sys.exit(1)

    generated = 0
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

        activity_obj = {
            "week":           WEEK_NAME,
            "activity_id":    aid,
            "name":           meta["name"],
            "date":           meta["date"],
            "start_time_utc": meta["start_time_utc"],
            "start_time":     meta["start_time"],
            "type":           meta["type"],
            "laps":           csv_data["laps"],
            "summary":        csv_data["summary"],
        }

        out_file = output_dir / f"{WEEK_NAME}_activity_{aid}.json"
        with open(out_file, "w", encoding="utf-8") as out:
            json.dump(activity_obj, out, ensure_ascii=False, indent=2)

        print(f"     ✓  {out_file.name}")
        generated += 1

    print(f"\n[OK] {generated} JSON generati in: {output_dir}")


if __name__ == "__main__":
    main()
