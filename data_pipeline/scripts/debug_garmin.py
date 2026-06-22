import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))
import firebase_admin
from firebase_admin import credentials, firestore
from garmin_sync import GarminSync

def main():
    sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')
    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    
    garmin = GarminSync(email=email, password=password, db=db, user_id="athlete_main")
    garmin.login()
    
    date_str = "2026-06-05" # A day we know we synced
    
    print("--- RHR ---")
    try:
        rhr = garmin.client.get_rhr_day(date_str)
        print("RHR day:", rhr)
    except Exception as e:
        print("RHR error:", e)
        
    print("--- Body Battery ---")
    try:
        bb = garmin.client.get_body_battery(date_str)
        print("Body Battery:", str(bb)[:500])
    except Exception as e:
        print("Body Battery error:", e)

    print("--- Stats (Heart Rate) ---")
    try:
        hr = garmin.client.get_heart_rates(date_str)
        print("HR:", str(hr)[:500])
    except Exception as e:
        print("HR error:", e)

if __name__ == "__main__":
    main()
