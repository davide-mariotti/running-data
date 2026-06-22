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
    
    print([m for m in dir(garmin.client) if 'user' in m.lower() or 'zone' in m.lower() or 'heart' in m.lower()])

if __name__ == "__main__":
    main()
