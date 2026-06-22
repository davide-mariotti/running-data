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
    
    print("--- WEEKLY LOAD ---")
    wl = db.collection("athletes").document(user_id).collection("weekly_load").document("latest").get()
    if wl.exists:
        print(wl.to_dict())
    else:
        print("weekly_load/latest not found")
        
    print("\n--- BODY BATTERY (latest) ---")
    bb_docs = list(db.collection("athletes").document(user_id).collection("body_battery").order_by("date", direction=firestore.Query.DESCENDING).limit(1).stream())
    if bb_docs:
        print(bb_docs[0].to_dict())
    else:
        print("no body battery docs")

if __name__ == "__main__":
    main()
