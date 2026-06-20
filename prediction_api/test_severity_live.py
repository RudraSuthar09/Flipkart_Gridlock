import requests, json

print('--- /traffic-severity/health ---')
r = requests.get('http://127.0.0.1:8001/api/v1/traffic-severity/health', timeout=10)
print(json.dumps(r.json(), indent=2))

print()
print('--- /traffic-severity/predict top_n=5 ---')
r2 = requests.get(
    'http://127.0.0.1:8001/api/v1/traffic-severity/predict',
    params={'timestamp': '2024-03-26T14:00:00', 'top_n': 5},
    timeout=60,
)
for row in r2.json():
    rank = row['rank_lightgbm']
    loc  = row['location_key'][:42]
    sev  = row['lightgbm_prediction']
    lane = row.get('lane_count')
    veh  = row.get('dominant_vehicle_cat') or '?'
    vio  = (row.get('dominant_violation') or '')[:30]
    print(f'  [{rank}] {loc:<42}  sev={sev:.4f}  lanes={lane}  veh={veh}  vio={vio}')

print()
print('--- /traffic-severity/locations (first 3) ---')
r3 = requests.get('http://127.0.0.1:8001/api/v1/traffic-severity/locations', timeout=30)
locs = r3.json()
print(f'  Total: {len(locs)} locations')
for loc in locs[:3]:
    print(f'  {loc["location_key"][:38]:<38} lane={loc.get("lane_count")}  veh={loc.get("dominant_vehicle_cat")}')
