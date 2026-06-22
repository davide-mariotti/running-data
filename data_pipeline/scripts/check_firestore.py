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
    
    collections = ['sleep', 'hrv', 'body_battery', 'stress', 'resting_hr', 'runs']
    print("Firestore Data Check:")
    for col in collections:
        docs = list(db.collection("athletes").document(user_id).collection(col).stream())
        print(f"Collection '{col}': {len(docs)} documents")
        if docs:
            print("  Sample doc:")
            print(" ", docs[0].id, "=>", docs[0].to_dict())

if __name__ == "__main__":
    main()
