import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))
import firebase_admin
from firebase_admin import credentials, firestore
from garmin_sync import GarminSync
from datetime import datetime, timedelta

def main():
    sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')
    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    user_id = "athlete_main"
    
    garmin = GarminSync(email=email, password=password, db=db, user_id=user_id)
    garmin.login()
    
    print("💓 Ricreo profilo atleta con nuove zone...")
    zones = garmin.detect_hr_zones()
    if zones:
        profile = {
            "name": "Davide",
            "z2_ceiling": zones.get("z2_ceiling", 150),
            "lthr": zones.get("lthr", 170),
            "max_hr": zones.get("max_hr", 190),
            "easy_pace": "6:30",
            "threshold_pace": "4:45",
            "auto_detected": True,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("athletes").document(user_id).set(profile, merge=True)
        print("✅ Profilo creato!", zones)
        
    print("🔄 Sincronizzo Body Battery e RHR per gli ultimi 60 giorni...")
    today = datetime.now().date()
    for i in range(60):
        day = today - timedelta(days=i)
        day_str = day.isoformat()
        try:
            garmin._sync_body_battery(day_str)
            garmin._sync_resting_hr(day_str)
            if i % 10 == 0:
                print(f"Progresso: {i}/60 giorni ({day_str})")
        except Exception as e:
            print(f"Errore {day_str}: {e}")

    print("✅ FIX COMPLETATO!")

if __name__ == "__main__":
    main()
