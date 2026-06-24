import firebase_admin
from firebase_admin import credentials, firestore

try:
    firebase_admin.initialize_app(credentials.Certificate('service-account.json'))
except ValueError:
    pass

db = firestore.client()
runs = list(db.collection('athletes/athlete_main/runs').stream())

ids = [r.id for r in runs]
print(f"Total documents: {len(ids)}")
print(f"Unique doc IDs: {len(set(ids))}")

activity_ids = [r.to_dict().get('activity_id') for r in runs]
print(f"Total activity_ids: {len(activity_ids)}")
print(f"Unique activity_ids: {len(set(activity_ids))}")

# Let's find documents that have the same activity_id but different doc IDs
from collections import defaultdict
act_to_doc = defaultdict(list)
for r in runs:
    aid = r.to_dict().get('activity_id')
    act_to_doc[aid].append(r.id)

for aid, docs in act_to_doc.items():
    if len(docs) > 1:
        print(f"Activity ID {aid} is in docs: {docs}")
