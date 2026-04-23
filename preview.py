import json

with open("output/W01.json", encoding="utf-8") as f:
    d = json.load(f)

a = d["activities"][0]
print("=== METADATI ATTIVITA ===")
print("  ID:          ", a["activity_id"])
print("  Nome:        ", a["name"])
print("  Data:        ", a["date"])
print("  Ora start:   ", a["start_time"], "UTC")
print("  Tipo:        ", a["type"])
print("  N. lap:      ", len(a["laps"]))
print("  N. punti GPS:", len(a["track_points"]))
print()
print("=== PRIMO LAP ===")
print(json.dumps(a["laps"][0], ensure_ascii=False, indent=2))
print()
print("=== RIEPILOGO ===")
print(json.dumps(a["summary"], ensure_ascii=False, indent=2))
print()
print("=== PRIMO PUNTO GPS ===")
print(json.dumps(a["track_points"][0], ensure_ascii=False, indent=2))
