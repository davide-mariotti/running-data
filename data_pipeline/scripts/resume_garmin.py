import sys
import os
from datetime import datetime

# Aggiungi functions al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))

import firebase_admin
from firebase_admin import credentials, firestore
from garmin_sync import GarminSync
from compute_load import compute_weekly_load

def main():
    print("🚀 Ripresa Sync con i token salvati...")
    sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')
    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    user_id = "athlete_main"
    
    garmin = GarminSync(email=email, password=password, db=db, user_id=user_id)
    
    try:
        # Usa i token da firestore, bypassa il login rate limited
        garmin.login()
        print("✅ Connesso a Garmin con i token precedenti!")
        
        print("💓 Ricreo profilo atleta...")
        zones = garmin.detect_hr_zones()
        if zones:
            profile = {
                "name": "Davide",
                "z2_ceiling": zones.get("z2_ceiling", 150),
                "lthr": zones.get("lthr", 170),
                "max_hr": zones.get("max_hr", 190),
                "resting_hr": zones.get("resting_hr", 50),
                "z1_bottom": zones.get("z1_bottom"),
                "z2_bottom": zones.get("z2_bottom"),
                "z3_bottom": zones.get("z3_bottom"),
                "z4_bottom": zones.get("z4_bottom"),
                "z5_bottom": zones.get("z5_bottom"),
                "easy_pace": "6:30",
                "threshold_pace": "4:45",
                "auto_detected": True,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            db.collection("athletes").document(user_id).set(profile, merge=True)
            print("✅ Profilo creato!")
        
        print("🔄 Sincronizzo gli ultimi 60 giorni di dati...")
        from datetime import timedelta
        today = datetime.now().date()
        for i in range(60):
            day = today - timedelta(days=i)
            day_str = day.isoformat()
            print(f"Sincronizzo {day_str}...")
            res = garmin.sync_day(day_str)
            print(f"Risultati sync per {day_str}: {res}")
        
        print("⚡ Ricalcolo carico...")
        compute_weekly_load(db, user_id, today.isoformat())
        
        print("✅ TUTTO PRONTO! La dashboard ora ha i dati.")
        
    except Exception as e:
        print(f"Errore: {e}")

if __name__ == "__main__":
    main()
