#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
organize_inbox.py — Smista attività Garmin in cartelle ANNO/Wxx/
================================================================
UTILIZZO:
  1. Scarica i file da Garmin Connect (CSV + GPX) in una cartella "inbox/"
     nella root del progetto (o in qualsiasi percorso).
  2. Esegui:
       python organize_inbox.py
     Oppure specifica una cartella sorgente diversa:
       python organize_inbox.py --inbox C:/Downloads/garmin_export

  Lo script legge la data di ogni attività dal file GPX e sposta la coppia
  (CSV + GPX) nella cartella corretta: <ANNO>/W<xx>/

  Usa --copy per copiare i file invece di spostarli (default: sposta).
  Usa --dry-run per vedere cosa farebbe senza modificare nulla.

ESEMPIO OUTPUT:
  [OK] activity_123.csv/.gpx  →  2025/W14/  (2025-04-05, running)
  [OK] activity_456.csv/.gpx  →  2024/W47/  (2024-11-20, cycling)
  [SKIP] activity_789: già presente in 2025/W22/
"""

import io, sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path


# ── Helpers ────────────────────────────────────────────────────────────────────

def calendar_week_folder(date_str: str) -> tuple[str, str]:
    """
    Dato "2025-04-05" restituisce ("2025", "W14").
    Usa la logica da calendario reale: l'1 Gennaio è sempre in W01.
    Ogni Lunedì inizia una nuova settimana.
    I giorni di fine anno che cadono nella settimana del 1 Gennaio successivo 
    vengono accorpati alla W01 dell'anno successivo.
    """
    from datetime import timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Trova il lunedì della settimana che contiene l'1 Gennaio dell'anno corrente
    jan1 = datetime(d.year, 1, 1)
    start_w1 = jan1 - timedelta(days=jan1.weekday())
    
    # Trova il lunedì della settimana che contiene l'1 Gennaio del PROSSIMO anno
    jan1_next = datetime(d.year + 1, 1, 1)
    start_w1_next = jan1_next - timedelta(days=jan1_next.weekday())
    
    if d >= start_w1_next:
        # Se cade nella settimana che contiene l'1 Gennaio dell'anno prossimo,
        # la accorpiamo alla W01 dell'anno prossimo (es. ex W53).
        year = str(d.year + 1)
        week = "W01"
    else:
        year = str(d.year)
        days_since_w1 = (d - start_w1).days
        week_num = (days_since_w1 // 7) + 1
        week = f"W{week_num:02d}"
        
    return year, week


def read_gpx_date(gpx_path: Path) -> str | None:
    """
    Legge la data dell'attività dal campo <metadata><time> del file GPX.
    Restituisce una stringa "YYYY-MM-DD" o None se non trovata.
    """
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
        # Estrai namespace dall'elemento root
        tag = root.tag
        ns = tag.split("}")[0].lstrip("{") if "}" in tag else "http://www.topografix.com/GPX/1/1"

        # Prova prima <metadata><time>
        time_el = root.find(f"{{{ns}}}metadata/{{{ns}}}time")

        # Fallback: primo <trkpt time=...>
        if time_el is None:
            for trkpt in root.iter(f"{{{ns}}}trkpt"):
                t = trkpt.find(f"{{{ns}}}time")
                if t is not None:
                    time_el = t
                    break

        if time_el is not None and time_el.text:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", time_el.text.strip())
            if m:
                return m.group(1)
    except Exception as e:
        print(f"  [WARN] Errore lettura GPX {gpx_path.name}: {e}")
    return None


def find_pairs(inbox: Path) -> dict[str, dict]:
    """
    Trova tutte le coppie CSV+GPX nella cartella inbox.
    Restituisce un dict: activity_id -> {"csv": Path, "gpx": Path}
    """
    pairs = {}
    for f in inbox.iterdir():
        if not f.is_file():
            continue
        m = re.match(r"activity_(\d+)\.(csv|gpx)$", f.name, re.IGNORECASE)
        if m:
            aid = m.group(1)
            ext = m.group(2).lower()
            if aid not in pairs:
                pairs[aid] = {}
            pairs[aid][ext] = f
    return pairs


def check_already_exists(aid: str, base_dir: Path) -> Path | None:
    """
    Controlla se un'attività è già stata processata in qualche cartella ANNO/Wxx/.
    Restituisce il path della cartella di destinazione se trovata, altrimenti None.
    """
    for year_dir in base_dir.iterdir():
        if not year_dir.is_dir() or not re.match(r"^\d{4}$", year_dir.name):
            continue
        for week_dir in year_dir.iterdir():
            if not week_dir.is_dir():
                continue
            if (week_dir / f"activity_{aid}.csv").exists() or \
               (week_dir / f"activity_{aid}.gpx").exists():
                return week_dir
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Smista file Garmin (CSV+GPX) dalla inbox in cartelle ANNO/Wxx/"
    )
    parser.add_argument(
        "--inbox", default="inbox",
        help="Cartella sorgente dei file (default: ./inbox)"
    )
    parser.add_argument(
        "--copy", action="store_true",
        help="Copia i file invece di spostarli"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra cosa farebbe senza modificare nulla"
    )
    args = parser.parse_args()

    root_dir = Path(__file__).parent.parent
    data_dir = root_dir / "data"
    inbox    = Path(args.inbox)
    if not inbox.is_absolute():
        inbox = data_dir / inbox.name

    print("\n" + "="*60)
    print("ORGANIZZAZIONE ATTIVITÀ GARMIN → ANNO/Wxx/")
    if args.dry_run:
        print("  *** DRY RUN — nessun file verrà modificato ***")
    if args.copy:
        print("  Modalità: COPIA (i file originali restano nell'inbox)")
    else:
        print("  Modalità: SPOSTA (i file vengono rimossi dall'inbox)")
    print("="*60)

    if not inbox.exists():
        print(f"\n[ERRORE] Cartella inbox non trovata: {inbox}")
        print("  Crea la cartella e mettici i file .csv e .gpx scaricati da Garmin.")
        sys.exit(1)

    pairs = find_pairs(inbox)
    if not pairs:
        print(f"\n[INFO] Nessuna coppia activity_*.csv + activity_*.gpx trovata in: {inbox}")
        sys.exit(0)

    print(f"\nTrovate {len(pairs)} attività nell'inbox: {inbox}\n")

    ok = skip = warn = 0

    for aid in sorted(pairs):
        fmap = pairs[aid]

        # Controlla che ci siano entrambi i file
        if "gpx" not in fmap:
            print(f"  [WARN] {aid}: manca il file GPX — skippato")
            warn += 1
            continue
        if "csv" not in fmap:
            print(f"  [WARN] {aid}: manca il file CSV — skippato")
            warn += 1
            continue

        # Controlla se già presente
        existing = check_already_exists(aid, data_dir)
        if existing:
            print(f"  [SKIP] activity_{aid}: già presente in {existing.relative_to(data_dir)}")
            skip += 1
            continue

        # Leggi la data dal GPX
        date_str = read_gpx_date(fmap["gpx"])
        if not date_str:
            print(f"  [WARN] activity_{aid}: impossibile leggere la data dal GPX — skippato")
            warn += 1
            continue

        year, week = calendar_week_folder(date_str)
        dest_dir   = data_dir / year / week

        if args.dry_run:
            print(f"  [DRY ] activity_{aid}.csv/.gpx  →  {year}/{week}/  ({date_str})")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            action = shutil.copy2 if args.copy else shutil.move
            for ext in ("csv", "gpx"):
                src = fmap[ext]
                dst = dest_dir / src.name
                action(str(src), str(dst))
            print(f"  [OK]  activity_{aid}.csv/.gpx  →  {year}/{week}/  ({date_str})")

        ok += 1

    print(f"\n{'─'*60}")
    print(f"  Spostati/Copiati : {ok}")
    print(f"  Già presenti     : {skip}")
    print(f"  Avvisi/Saltati   : {warn}")
    print(f"{'─'*60}")

    if ok > 0 and not args.dry_run:
        print("\n[PROSSIMO PASSO] Riesegui lo script di conversione:")
        print("  python convert_all.py")
        print("\nIl dashboard_index.json verrà aggiornato con le nuove attività.")

    print()


if __name__ == "__main__":
    main()
