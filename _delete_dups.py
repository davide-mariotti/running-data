import firebase_admin
from firebase_admin import credentials, firestore

try:
    firebase_admin.initialize_app(credentials.Certificate('service-account.json'))
except ValueError:
    pass

db = firestore.client()
runs_ref = db.collection('athletes/athlete_main/runs')
runs = list(runs_ref.stream())

batch = db.batch()
count = 0
for r in runs:
    if '_' in r.id:
        print(f"Deleting duplicate doc: {r.id}")
        batch.delete(runs_ref.document(r.id))
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()

if count % 400 != 0:
    batch.commit()

print(f"Deleted {count} duplicate documents.")
