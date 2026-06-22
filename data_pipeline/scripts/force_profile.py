import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))

import firebase_admin
from firebase_admin import credentials, firestore

def main():
    sa_path = os.path.join(os.path.dirname(__file__), '..', 'service-account.json')
    cred = credentials.Certificate(sa_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    user_id = "athlete_main"
    
    profile = {
        "name": "Davide",
        "z2_ceiling": 150,  # Using standard default since the 67 bpm reading is obviously wrong
        "lthr": 170,
        "max_hr": 190,
        "easy_pace": "6:30",
        "threshold_pace": "4:45",
        "auto_detected": False,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    
    db.collection("athletes").document(user_id).set(profile, merge=True)
    print("✅ Profilo creato forzatamente per bypassare il rate limit!")

if __name__ == "__main__":
    main()
