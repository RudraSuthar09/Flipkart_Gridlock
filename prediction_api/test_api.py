import requests
import json

print("--- /health ---")
r = requests.get("http://127.0.0.1:8001/api/v1/health", timeout=10)
print(json.dumps(r.json(), indent=2))

print()
print("--- /predict top_n=5 ---")
r2 = requests.get(
    "http://127.0.0.1:8001/api/v1/predict",
    params={"timestamp": "2024-03-26T14:00:00", "top_n": 5},
    timeout=30,
)
for row in r2.json():
    print(f"  [{row['rank_lightgbm']}] {row['location_key'][:42]:<42}  lgbm={row['lightgbm_prediction']:.4f}  naive={row['naive_prediction']:.1f}")

print()
print("--- /locations ---")
r3 = requests.get("http://127.0.0.1:8001/api/v1/locations", timeout=30)
locs = r3.json()
print(f"  Total: {len(locs)} locations  HTTP {r3.status_code}")
print(f"  Sample: {locs[0]}")
