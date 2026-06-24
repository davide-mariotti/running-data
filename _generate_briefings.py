import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path("backend").resolve()))
sys.path.insert(0, str(Path("data_pipeline").resolve()))

import firebase_admin
from firebase_admin import credentials, firestore
from coach_brain import assess_readiness

def main():
    sa_path = "service-account.json"
    if os.path.exists(sa_path):
        try:
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
        except ValueError:
            pass
            
    db = firestore.client()
    user_id = "athlete_main"
    
    # Try to get API KEY
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        env_path = Path(".env")
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=")[1]
                        break

    if not api_key:
        print("No GEMINI_API_KEY found.")
        return

    today = datetime.now()
    for i in reversed(range(7)):
        d_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if i == 0:
            print(f"Generating for today: {d_str}")
            assess_readiness(db, user_id, api_key, target_date=d_str)
        else:
            b_doc = db.collection(f"athletes/{user_id}/briefings").document(d_str).get()
            if not b_doc.exists:
                print(f"Missing briefing for {d_str}, generating...")
                assess_readiness(db, user_id, api_key, target_date=d_str)
            else:
                print(f"Briefing for {d_str} already exists.")

if __name__ == "__main__":
    main()
