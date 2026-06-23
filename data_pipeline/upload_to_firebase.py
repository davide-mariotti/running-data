import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, firestore

root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir / "backend"))

try:
    from compute_load import compute_weekly_load
except ImportError:
    print("ERRORE: Impossibile importare compute_load. Assicurati di lanciare lo script dalla cartella data_pipeline o root.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_ID = "athlete_main"

def parse_time_to_min(t_str):
    if not t_str: return 0.0
    try:
        parts = str(t_str).split(':')
        if len(parts) == 3:
            h, m, s = parts
            return int(h)*60 + int(m) + float(s)/60
        elif len(parts) == 2:
            m, s = parts
            return int(m) + float(s)/60
    except Exception:
        pass
    return 0.0

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Upload to Firebase")
    parser.add_argument("--user_id", default="athlete_main", help="ID Atleta (es. UID Firebase o athlete_main)")
    parser.add_argument("--index_file", default=None, help="Path del dashboard_index.json")
    args = parser.parse_args()

    USER_ID = args.user_id

    logger.info("🔧 Inizializzazione Firebase Admin...")
    sa_path = root_dir / "service-account.json"
    if not sa_path.exists():
        logger.error(f"File non trovato: {sa_path}")
        sys.exit(1)
        
    cred = credentials.Certificate(str(sa_path))
    try:
        firebase_admin.initialize_app(cred)
    except ValueError:
        pass
    
    db = firestore.client()

    logger.info(f"📂 Lettura indice dashboard_index.json per utente: {USER_ID}")
    idx_path = Path(args.index_file) if args.index_file else (root_dir / "frontend" / "dashboard_index.json")
    if not idx_path.exists():
        logger.error("Indice non trovato. Lancia prima convert_all.py!")
        sys.exit(1)
        
    with open(idx_path, "r", encoding="utf-8") as f:
        raw_json = f.read()
        activities = json.loads(raw_json)

    # Se non è l'admin, salviamo il dashboard_index intero su Firestore (come stringa per caricamento rapido)
    if USER_ID != "athlete_main":
        logger.info(f"Salvataggio index_data su Firestore per {USER_ID}...")
        db.collection(f"athletes/{USER_ID}/index_data").document("dashboard_index").set({
            "data": raw_json,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

    logger.info(f"🚀 Inizio caricamento {len(activities)} attività su Firebase...")
    
    batch = db.batch()
    count = 0
    for act in activities:
        act_id = str(act["activity_id"])
        doc_ref = db.collection(f"athletes/{USER_ID}/runs").document(act_id)
        
        summary = act.get("summary", {})
        
        # Mappatura dei campi chiave usati da compute_load.py e dalla vecchia app
        dist = summary.get("distanza_km", 0)
        if not dist: 
            dist = float(summary.get("distanza_m", 0)) / 1000.0 if summary.get("distanza_m") else 0
        
        time_str = summary.get("tempo_in_movimento") or summary.get("tempo")
        duration_min = parse_time_to_min(time_str)
        
        avg_hr = summary.get("fc_media_bpm", 0)
        
        data = {
            "activity_id": act_id,
            "date": act.get("date", ""),
            "sport": act.get("sport", "running"),
            "name": act.get("name", ""),
            "distance_km": float(dist) if dist else 0.0,
            "duration_min": round(duration_min, 2),
            "avg_hr": float(avg_hr) if avg_hr else 0.0,
            "updated_from_local": firestore.SERVER_TIMESTAMP
        }
        
        batch.set(doc_ref, data, merge=True)
        count += 1
        
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()

    if count % 400 != 0:
        batch.commit()

    logger.info(f"✅ Upload completato ({count} attività).")

    # Ricalcola ACWR
    tz = ZoneInfo("Europe/Rome")
    today_str = datetime.now(tz).strftime("%Y-%m-%d")
    
    logger.info("⚡ Calcolo ACWR (Acute:Chronic Workload Ratio) in corso...")
    compute_weekly_load(db, USER_ID, today_str)

    # Genera il briefing reale tramite Gemini se l'API key è disponibile
    env_path = root_dir / ".env"
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.strip().split("=")[1]
                    break

    if api_key:
        logger.info("📋 Generazione Briefing REALE con Gemini in corso...")
        try:
            from coach_brain import assess_readiness
            assess_readiness(db, USER_ID, api_key)
        except Exception as e:
            logger.error(f"Errore durante la generazione del briefing AI: {e}")
    else:
        logger.warning("⚠️ Nessuna GEMINI_API_KEY trovata nel file .env, genero un briefing fittizio...")
        briefing_ref = db.collection(f"athletes/{USER_ID}/briefings").document(today_str)
        briefing_data = {
            "date": today_str,
            "readiness": "GREEN",
            "analysis": "✅ **Dati Sincronizzati Correttamente col Cloud**\n\n_Non è stata trovata una chiave Gemini, quindi questo è un messaggio di sistema._",
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        briefing_ref.set(briefing_data)

    # Aggiorna lo stato globale di sincronizzazione per la Dashboard
    logger.info("🔄 Aggiornamento stato di sincronizzazione globale...")
    try:
        db.collection("system").document("last_sync").set({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "success",
            "message": "Sincronizzato tramite script Python locale"
        }, merge=True)
    except Exception as e:
        logger.warning(f"Impossibile aggiornare system/last_sync: {e}")

    logger.info("🎉 Processo completato! La tua dashboard ora dovrebbe funzionare.")

if __name__ == "__main__":
    main()
