import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add functions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data_pipeline'))

import firebase_admin
from firebase_admin import credentials, firestore
from garmin_sync import GarminSync

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def load_existing_activity_ids(index_path):
    """Carica gli ID e trova l'ultima data."""
    existing_ids = set()
    latest_date = None
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for act in data:
                    if act.get("activity_id"):
                        existing_ids.add(str(act.get("activity_id")))
                    # Cerca l'ultima data
                    d = act.get("date")
                    if d:
                        if not latest_date or d > latest_date:
                            latest_date = d
        except Exception as e:
            logger.warning(f"Impossibile leggere l'index: {e}")
    return existing_ids, latest_date

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto Fetch")
    parser.add_argument("--user_id", default="athlete_main")
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--work_dir", default=None, help="Directory di lavoro base")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🏃 AGENTIC RUNNING COACH — Auto Fetch ({args.user_id})")
    print("=" * 60)

    # 1. Init Firebase
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
    if not os.path.exists(sa_path):
        # Fallback al percorso assoluto
        sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')
    
    if os.path.exists(sa_path):
        try:
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase inizializzato")
        except ValueError:
            pass # Già inizializzato
    db = firestore.client()

    email = args.email or os.environ.get("GARMIN_EMAIL")
    password = args.password or os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        logger.error("❌ Credenziali Garmin non fornite")
        sys.exit(1)

    user_id = args.user_id
    work_dir = args.work_dir

    # 2. Setup GarminSync
    sync = GarminSync(email, password, db, user_id)
    try:
        sync.login()
    except Exception as e:
        logger.error(f"❌ Errore login Garmin: {e}")
        sys.exit(1)

    # 3. Sync Health Data for last 5 days
    logger.info("🔄 Sincronizzazione metriche vitali degli ultimi 5 giorni...")
    today = datetime.now()
    for i in range(5):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        sync.sync_day(day_str)

    # 4. Scarica nuove attività in formato ZIP/FIT o JSON
    logger.info("📥 Controllo nuove attività...")
    
    # Imposta i path in base al work_dir
    if work_dir:
        base_dir = Path(work_dir)
        index_path = base_dir / "dashboard_index.json"
        inbox_dir = base_dir / "inbox"
        data_dir = base_dir / "data"
    else:
        base_dir = Path(__file__).parent.parent
        index_path = base_dir / "frontend" / "dashboard_index.json"
        inbox_dir = base_dir / "data" / "inbox"
        data_dir = base_dir / "data"
        
    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    
    existing_ids, latest_date = load_existing_activity_ids(str(index_path))
    
    activities_fetched = 0
    end_date = today.strftime("%Y-%m-%d")
    
    # Se abbiamo già dati, cerchiamo dagli ultimi 10 giorni rispetto all'ultimo allenamento salvato
    # Altrimenti partiamo dal 2010 per scaricare tutto lo storico
    if latest_date:
        last_d = datetime.strptime(latest_date, "%Y-%m-%d")
        start_date = (last_d - timedelta(days=10)).strftime("%Y-%m-%d")
    else:
        start_date = "2010-01-01"
        
    logger.info(f"📅 Ricerca attività da {start_date} a {end_date}...")
    
    try:
        activities = sync.client.get_activities_by_date(start_date, end_date)
        if activities:
            for act in activities:
                act_id = str(act.get("activityId", ""))
                if not act_id:
                    continue
                    
                if act_id not in existing_ids:
                    logger.info(f"   ⬇️ Scarico nuova attività: {act_id} ({act.get('activityName', '')})")
                    try:
                        from garminconnect import Garmin
                        csv_data = sync.client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.CSV)
                        csv_path = os.path.join(inbox_dir, f"activity_{act_id}.csv")
                        with open(csv_path, "wb") as f:
                            f.write(csv_data)
                            
                        try:
                            gpx_data = sync.client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)
                            gpx_path = os.path.join(inbox_dir, f"activity_{act_id}.gpx")
                            with open(gpx_path, "wb") as f:
                                f.write(gpx_data)
                        except Exception as e:
                            logger.warning(f"      ⚠️ Impossibile scaricare GPX per {act_id}: {e}")

                        activities_fetched += 1
                        logger.info(f"      ✅ Salvati file CSV/GPX per {act_id} in inbox")
                    except Exception as download_err:
                        logger.error(f"      ❌ Errore download {act_id}: {download_err}")
    except Exception as e:
        logger.error(f"❌ Errore recupero lista attività: {e}")
        sys.exit(1)

    # 5. Esegui la pipeline
    logger.info("⚙️ Avvio pipeline di conversione dati...")
    
    import subprocess
    def run_script(script_name, args_list):
        script_path = os.path.join(os.path.dirname(__file__), script_name)
        cmd = [sys.executable, script_path] + args_list
        logger.info(f"Esecuzione: {' '.join(cmd)}")
        res = subprocess.run(cmd)
        if res.returncode != 0:
            logger.error(f"❌ Errore nello script {script_name}")
            
    run_script("organize_inbox.py", ["--inbox", str(inbox_dir), "--data_dir", str(data_dir)])
    run_script("convert_all.py", ["--data_dir", str(data_dir), "--index_file", str(index_path)])
    run_script("upload_to_firebase.py", ["--user_id", user_id, "--index_file", str(index_path)])
    
    # generate_diary solo per l'admin (se necessario), oppure disabilitato per i temp
    if not work_dir:
        run_script("generate_diary.py", [])

    # coach_brain viene eseguito alla fine o come step separato
    from coach_brain import assess_readiness
    logger.info("🧠 Avvio Coach Brain...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            assess_readiness(db, user_id, api_key)
        except Exception as e:
            logger.error(f"❌ Errore Coach Brain: {e}")
    else:
        logger.warning("Nessuna GEMINI_API_KEY trovata. Coach Brain saltato.")

    logger.info(f"🎉 Auto-Fetch completato con successo per {user_id}!")

if __name__ == "__main__":
    main()
