"""Quick API validation test."""
import requests

BASE = "http://127.0.0.1:8001"

# Count predictions
r = requests.get(f"{BASE}/api/v1/predict", params={"timestamp": "2024-03-26T14:00:00", "top_n": 10}, timeout=60)
data = r.json()
print("=== COUNT predictions at 2024-03-26T14:00 ===")
for p in data:
    print(f"  [{p['rank_lightgbm']:3}] {p['location_key'][:40]:<40} lgbm={p['lightgbm_prediction']:7.2f} naive={p['naive_prediction']:5.1f}")

print()
print("=== SEVERITY predictions at 2024-03-26T14:00 ===")
r2 = requests.get(f"{BASE}/api/v1/traffic-severity/predict", params={"timestamp": "2024-03-26T14:00:00", "top_n": 10}, timeout=60)
data2 = r2.json()
for p in data2:
    print(f"  [{p['rank_lightgbm']:3}] {p['location_key'][:40]:<40} sev={p['lightgbm_prediction']:7.3f} naive={p['naive_prediction']:5.3f}")
