"""Quick test script for AWR upload endpoints."""
import requests
import json
import sys

BASE = "http://127.0.0.1:8000"

# Test 1: Single upload
print("=== Test 1: Single AWR Upload ===")
with open(r"C:\Users\1039081\Downloads\AWR_NGD.html", "rb") as f:
    resp = requests.post(
        f"{BASE}/api/upload/awr",
        files={"file": ("AWR_NGD.html", f, "text/html")},
        data={"label": "test_good"},
        timeout=30,
    )

if resp.status_code == 200:
    data = resp.json()
    print(f"  Status: {data['status']}")
    print(f"  DB Name: {data['db_name']}")
    print(f"  Instance: {data['instance']}")
    print(f"  Snap Range: {data['snap_range']}")
    print(f"  Elapsed Min: {data['elapsed_min']}")
    print(f"  DB Time Min: {data['db_time_min']}")
    print(f"  Health Score: {data['health']['score']}")
    print(f"  Health Grade: {data['health']['grade']}")
    print(f"  # Recommendations: {len(data['recommendations'])}")
    print(f"  # Insights: {len(data['insights'])}")
    for i, ins in enumerate(data["insights"][:3]):
        print(f"    Insight {i+1}: [{ins['severity']}] {ins['title']}")
else:
    print(f"  ERROR {resp.status_code}: {resp.text[:500]}")

# Test 2: Two-file comparison
print("\n=== Test 2: AWR Comparison Upload ===")
with open(r"C:\Users\1039081\Downloads\AWR_NGD.html", "rb") as good, \
     open(r"C:\Users\1039081\Downloads\awr_SCTASK0161379.html", "rb") as bad:
    resp = requests.post(
        f"{BASE}/api/upload/compare",
        files={
            "good_file": ("AWR_NGD.html", good, "text/html"),
            "bad_file": ("awr_SCTASK0161379.html", bad, "text/html"),
        },
        timeout=30,
    )

if resp.status_code == 200:
    data = resp.json()
    print(f"  Status: {data['status']}")
    print(f"  Health Good: {data['health_good']['score']} ({data['health_good']['grade']})")
    print(f"  Health Bad: {data['health_bad']['score']} ({data['health_bad']['grade']})")
    print(f"  # Recommendations: {len(data['recommendations'])}")
    print(f"  # Insights: {len(data['insights'])}")
    for i, ins in enumerate(data["insights"][:3]):
        print(f"    Insight {i+1}: [{ins['severity']}] {ins['title']}")
    report = data["report"]
    print(f"  DB Time Change: {report.get('db_time_change_pct', 'N/A')}%")
    print(f"  # SQL Regressions: {len(report.get('sql_regressions', []))}")
    print(f"  # Wait Regressions: {len(report.get('wait_regressions', []))}")
else:
    print(f"  ERROR {resp.status_code}: {resp.text[:500]}")

print("\n=== Tests Complete ===")
