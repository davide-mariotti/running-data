import os
import sys
import json
import logging
from datetime import datetime, timedelta

# Add functions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'data_pipeline'))

import firebase_admin
from firebase_admin import credentials, firestore
from garmin_sync import GarminSync

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def load_existing_activity_ids(index_path):
    """Carica gli ID delle attività già presenti in dashboard_index.json per evitare duplicati."""
    if not os.path.exists(index_path):
        return set()
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {str(act.get("activity_id")) for act in data if act.get("activity_id")}
    except Exception as e:
        logger.warning(f"Impossibile leggere l'index: {e}")
        return set()

def main():
    print("=" * 60)
    print("🏃 AGENTIC RUNNING COACH — Auto Fetch (GitHub Actions)")
    print("=" * 60)

    # 1. Init Firebase
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json")
    if not os.path.exists(sa_path):
        logger.error(f"❌ File service-account.json non trovato in {sa_path}")
        sys.exit(1)

    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("✅ Firebase inizializzato")

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        logger.error("❌ Credenziali Garmin non fornite via ENV (GARMIN_EMAIL, GARMIN_PASSWORD)")
        sys.exit(1)

    user_id = os.environ.get("ATHLETE_USER_ID", "athlete_main")

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
    index_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dashboard_index.json')
    existing_ids = load_existing_activity_ids(index_path)
    
    inbox_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'inbox')
    os.makedirs(inbox_dir, exist_ok=True)
    
    activities_fetched = 0
    # Cerca attività negli ultimi 5 giorni
    start_date = (today - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
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
                        # Scarica CSV e GPX per essere compatibile con organize_inbox
                        from garminconnect import Garmin
                        
                        # Download CSV
                        csv_data = sync.client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.CSV)
                        csv_path = os.path.join(inbox_dir, f"activity_{act_id}.csv")
                        with open(csv_path, "wb") as f:
                            f.write(csv_data)
                            
                        # Download GPX (non tutte le attività lo hanno, ma proviamo)
                        try:
                            gpx_data = sync.client.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)
                            gpx_path = os.path.join(inbox_dir, f"activity_{act_id}.gpx")
                            with open(gpx_path, "wb") as f:
                                f.write(gpx_data)
                        except Exception as e:
                            logger.warning(f"      ⚠️ Impossibile scaricare GPX per {act_id} (potrebbe essere indoor): {e}")

                        activities_fetched += 1
                        logger.info(f"      ✅ Salvati file CSV/GPX per {act_id} in inbox")
                    except Exception as download_err:
                        logger.error(f"      ❌ Errore download {act_id}: {download_err}")
    except Exception as e:
        logger.error(f"❌ Errore recupero lista attività: {e}")

    # 5. Esegui la pipeline locale solo se ci sono nuovi file (o per generare index aggiornato)
    logger.info("⚙️ Avvio pipeline di conversione dati...")
    
    scripts_dir = os.path.dirname(__file__)
    
    # organize_inbox
    import organize_inbox
    try:
        organize_inbox.main()
    except Exception as e:
        logger.error(f"❌ Errore in organize_inbox: {e}")
        
    # convert_all
    import convert_all
    try:
        convert_all.main()
    except Exception as e:
        logger.error(f"❌ Errore in convert_all: {e}")
        
    # upload_to_firebase (genera anche il briefing AI)
    import upload_to_firebase
    try:
        upload_to_firebase.main()
    except Exception as e:
        logger.error(f"❌ Errore in upload_to_firebase: {e}")

    # generate_diary
    import generate_diary
    try:
        generate_diary.main()
    except Exception as e:
        logger.error(f"❌ Errore in generate_diary: {e}")

    logger.info("🎉 Auto-Fetch completato con successo!")

if __name__ == "__main__":
    main()
