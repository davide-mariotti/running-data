import json

data = json.load(open('frontend/dashboard_index.json', 'r', encoding='utf-8'))
empty = [a for a in data if not a.get('summary')]
print(f"Empty summaries: {len(empty)}/{len(data)}")
for a in sorted(empty, key=lambda x: x.get('date', ''))[-10:]:
    print(f"  {a['date']} {a['sport']} id={a['activity_id']}")
