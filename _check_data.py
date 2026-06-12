import requests

# Get explicit demo comparison data
r = requests.get('http://localhost:8000/api/compare/mock', timeout=30)
r.raise_for_status()
data = r.json()

# Check the data structure
print('Keys:', list(data.keys()))
required = [
    'sources', 'report', 'health_good', 'health_bad',
    'recommendations', 'insights', 'comparison_rca', 'advanced',
]
for key in required:
    print(f'{key}: {"present" if key in data else "MISSING"}')

report = data.get('report', {})
top_wait_events = report.get('top_wait_events', {})
print(f'sources: {data.get("sources", {})}')
print(f'load_profile_delta: {len(report.get("load_profile_delta", []))}')
print(f'top_wait_events.comparisons: {len(top_wait_events.get("comparisons", []))}')
print(f'sql_regressions: {len(report.get("sql_regressions", []))}')
print(f'normalized_metrics: {len(report.get("normalized_comparison", {}).get("all_metrics", []))}')
