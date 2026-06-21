import requests

r = requests.get('http://127.0.0.1:8001/api/v1/predict?timestamp=2024-04-08T17:00:00')
data = r.json()
key = 'lightgbm_prediction'
sorted_data = sorted(data, key=lambda x: x[key], reverse=True)

print('Total locations:', len(data))
print()

# Top 100 coordinate spread
lats_100 = [d['latitude'] for d in sorted_data[:100]]
lngs_100 = [d['longitude'] for d in sorted_data[:100]]
print('TOP 100 lat range:', round(min(lats_100),4), 'to', round(max(lats_100),4), '  delta:', round(max(lats_100)-min(lats_100),4))
print('TOP 100 lng range:', round(min(lngs_100),4), 'to', round(max(lngs_100),4), '  delta:', round(max(lngs_100)-min(lngs_100),4))

# All coordinate spread
lats_all = [d['latitude'] for d in data]
lngs_all = [d['longitude'] for d in data]
print()
print('ALL lat range:', round(min(lats_all),4), 'to', round(max(lats_all),4), '  delta:', round(max(lats_all)-min(lats_all),4))
print('ALL lng range:', round(min(lngs_all),4), 'to', round(max(lngs_all),4), '  delta:', round(max(lngs_all)-min(lngs_all),4))

# Score distribution
scores = [d[key] for d in sorted_data]
print()
print('Score #1:', round(scores[0], 5))
print('Score #10:', round(scores[9], 5))
print('Score #50:', round(scores[49], 5))
print('Score #100:', round(scores[99], 5))
print('Score #500:', round(scores[499], 5))
print('Score #6333 (last):', round(scores[-1], 5))

# Count scores that are zero vs non-zero
nonzero = sum(1 for s in scores if s > 0.0001)
print()
print('Non-zero score locations:', nonzero, 'of', len(scores))
