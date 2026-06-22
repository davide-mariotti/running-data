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
    
    print("Profile Settings:")
    try:
        s = garmin.client.get_userprofile_settings()
        print(s)
    except Exception as e:
        print("Error profile settings:", e)
        
    print("\nUser Profile:")
    try:
        p = garmin.client.get_user_profile()
        print(p)
    except Exception as e:
        print("Error user profile:", e)

if __name__ == "__main__":
    main()
