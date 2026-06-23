#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Activity Converter Unificato - Genera JSON per Corsa, Bici e Nuoto
========================================================================
UTILIZZO:
  Lancia lo script dalla root del progetto:
    python convert_all.py
    
  Lo script processa in automatico tutte le attività presenti in cartelle anno:
  - <ANNO>/Wxx/ (es. 2026/W01/, 2027/W01/)
  
  Determina automaticamente lo sport leggendo il file GPX (running, cycling, swimming)
  ed esporta:
  - File individuali in output<ANNO>/Wxx/<Wxx>_<sport>_<ID>.json
  - Un indice leggero globale in dashboard_index.json per l'interfaccia web.
  
  Saltando le attività già convertite (cache) per velocizzare l'esecuzione.
"""

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
    # Comuni e Corsa
    "Lap":                                                 "lap",
    "Tempo":                                               "tempo",
    "Tempo cumulato":                                      "tempo_cumulato",
    "Distanza km":                                         "distanza_km",
    "Passo medio min/km":                                  "passo_medio",
    "PRP medio min/km":                                    "prp_medio",
    "FC Media bpm":                                        "fc_media_bpm",
    "FC Media":                                            "fc_media_bpm",
    "FC max bpm":                                          "fc_max_bpm",
    "FC max":                                              "fc_max_bpm",
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
    "Calorie":                                             "calorie",
    "Temperatura med":                                     "temperatura_med",
    "Passo migliore min/km":                               "passo_migliore",
    "Cadenza di corsa max pam":                            "cadenza_max_pam",
    "Tempo in movimento":                                  "tempo_in_movimento",
    "Passo medio in movimento min/km":                     "passo_medio_in_movimento",
    "Perdita velocità di passo media cm/s":                "perdita_velocita_cms",
    "Percentuale perdita velocità di passo media %":       "perdita_velocita_pct",
}

def normalize_key(k: str, sport: str) -> str:
    if not k:
        return None
    k = k.strip()
    
    # Specifici per sport
    if sport == "swimming":
        if k == "Distanza": return "distanza_m"
        if k == "Ripetute": return "lap"
        if k == "Stile": return "stile"
        if k == "Vasche": return "vasche"
        if k == "Passo medio": return "passo_medio"
        if k == "Passo migliore": return "passo_migliore"
        if k == "Swolf medio": return "swolf_medio"
        if k == "Totale bracciate": return "totale_bracciate"
        if k == "Bracciate medie": return "bracciate_medie"
    elif sport == "cycling":
        if k == "Distanza": return "distanza_km"
        if k == "Velocità media": return "velocita_media_kmh"
        if k == "Velocità max": return "velocita_max_kmh"
        if k == "Velocità media in movimento": return "velocita_media_movimento_kmh"
        if k == "Ascesa totale": return "ascesa_m"
        if k == "Discesa totale": return "discesa_m"
        if k == "Cadenza pedalata media": return "cadenza_pedalata_media_rpm"
        if k == "Cadenza pedalata max": return "cadenza_pedalata_max_rpm"
    
    mapped = CSV_KEY_MAP.get(k)
    if mapped:
        return mapped
        
    s = unicodedata.normalize("NFKD", k).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def clean_value(v: str):
    if v is None:
        return None
    v = v.strip()
    if v in ("--", "", "N/D"):
        return None
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
def parse_csv(csv_path: Path, sport: str) -> dict:
    laps, summary = [], None
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lap_label = row.get("Lap", row.get("Ripetute", "")).strip()
            record = {}
            for k, v in row.items():
                norm_k = normalize_key(k, sport)
                if norm_k:
                    record[norm_k] = clean_value(v)
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
    import argparse
    parser = argparse.ArgumentParser(description="Converti attività in JSON")
    parser.add_argument("--data_dir", default=None, help="Cartella dati base")
    parser.add_argument("--index_file", default=None, help="File destinazione per dashboard_index.json")
    args = parser.parse_args()

    root_dir = Path(__file__).parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else (root_dir / "data")
    frontend_dir = root_dir / "frontend"
    index_file = Path(args.index_file) if args.index_file else (frontend_dir / "dashboard_index.json")

    print("\n" + "="*50)
    print("INIZIO CONVERSIONE ATTIVITÀ (SETTIMANE UNIFICATE, MULTI-ANNO)")
    print("="*50)

    # Trova tutte le cartelle che hanno il nome di un anno a 4 cifre (es. 2026)
    year_dirs = [d for d in data_dir.iterdir() if d.is_dir() and re.match(r"^\d{4}$", d.name)]
    
    if not year_dirs:
        print("[ERRORE] Nessuna cartella anno trovata (es. 2026, 2027).")
        sys.exit(1)

    sport_short_map = {
        "running": "run",
        "cycling": "bike",
        "swimming": "swim"
    }

    count_processed = 0
    dashboard_index = []

    for year_dir in sorted(year_dirs):
        year = year_dir.name
        out_base = data_dir / f"output{year}"
        out_base.mkdir(exist_ok=True)
        
        print(f"\n--- Elaborazione Anno: {year} ---")

        week_dirs = sorted(
            [d for d in year_dir.iterdir() if d.is_dir() and re.match(r"W\d+", d.name)],
            key=lambda d: int(d.name[1:])
        )

        for week_dir in week_dirs:
            week_name = week_dir.name
            week_out = out_base / week_name
            week_out.mkdir(exist_ok=True)
            
            files_by_id = defaultdict(dict)
            for f in week_dir.iterdir():
                if not f.is_file():
                    continue
                m = re.match(r"activity_(\d+)\.(csv|gpx)", f.name, re.IGNORECASE)
                if m:
                    files_by_id[m.group(1)][m.group(2).lower()] = f

            for aid in sorted(files_by_id):
                fmap = files_by_id[aid]
                if "csv" not in fmap or "gpx" not in fmap:
                    print(f"  ! {week_name} - {aid}: CSV o GPX mancante, skip")
                    continue
    
                # Determina lo sport e il nome file in anticipo per leggere la cache correttamente
                existing_cache = list(week_out.glob(f"{week_name}_*_{aid}.json"))
                
                act_obj = None
                if existing_cache:
                    # Cache trovata
                    with open(existing_cache[0], "r", encoding="utf-8") as f:
                        act_obj = json.load(f)
                else:
                    meta = parse_gpx_meta(fmap["gpx"])
                    sport_raw = meta["type"] if meta["type"] else "running"
                    
                    if "swim" in sport_raw.lower():
                        sport = "swimming"
                    elif "cycl" in sport_raw.lower() or "bike" in sport_raw.lower() or "ride" in sport_raw.lower():
                        sport = "cycling"
                    else:
                        sport = "running"
                        
                    sport_short = sport_short_map.get(sport, sport)
                    date_short = meta["date"][2:] if meta["date"] else "00-00-00"
                    out_file = week_out / f"{week_name}_{date_short}_{sport_short}_{aid}.json"
                        
                    print(f"  -> [{week_name}] Parsing {sport} activity {aid} (original: {sport_raw})...")
                    
                    csv_data = parse_csv(fmap["csv"], sport)
    
                    act_obj = {
                        "week":           week_name,
                        "activity_id":    aid,
                        "sport":          sport,
                        "name":           meta["name"],
                        "date":           meta["date"],
                        "start_time_utc": meta["start_time_utc"],
                        "start_time":     meta["start_time"],
                        "type":           sport_raw,
                        "laps":           csv_data["laps"],
                        "summary":        csv_data["summary"],
                    }
                    
                    with open(out_file, "w", encoding="utf-8") as out:
                        json.dump(act_obj, out, ensure_ascii=False, indent=2)
                    
                    count_processed += 1
                    
                # Generazione Indice per Dashboard
                if act_obj:
                    summary = act_obj.get("summary")
                    if not summary and act_obj.get("laps"):
                        for l in act_obj["laps"]:
                            if l.get("lap") == "Riepilogo" or l.get("intervallo") == "Riepilogo":
                                summary = l
                                break
                                
                    index_entry = {
                        "activity_id": act_obj["activity_id"],
                        "year": year,
                        "week": act_obj["week"],
                        "sport": act_obj["sport"],
                        "name": act_obj.get("name"),
                        "date": act_obj.get("date"),
                        "start_time_utc": act_obj.get("start_time_utc"),
                        "summary": summary or {}
                    }
                    dashboard_index.append(index_entry)

    # Salva l'indice globale
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(dashboard_index, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Generati {count_processed} nuovi file JSON in totale.")
    print(f"[OK] Aggiornato dashboard_index.json con {len(dashboard_index)} attività.")
    print("\n" + "="*50)
    print("[COMPLETATO] Tutte le conversioni aggiornate.")
    print("="*50 + "\n")


if __name__ == "__main__":
    main()
