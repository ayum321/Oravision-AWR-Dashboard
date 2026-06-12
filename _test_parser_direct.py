"""Direct test of parser output."""
import sys
sys.path.insert(0, "backend")
from services.html_parser import parse_awr_html, normalize_parsed_data

with open(r"C:\Users\1039081\Downloads\BAD.html", "r", encoding="utf-8", errors="replace") as f:
    raw = parse_awr_html(f.read())

d = normalize_parsed_data(raw).model_dump()
sqls = d.get("sql_stats", [])
print(f"SQL count: {len(sqls)}")
for s in sqls[:5]:
    sid = s.get("sql_id", "?")
    rank = s.get("_elapsed_rank", "?")
    appeared = s.get("_appeared_in", "?")
    source = s.get("_source", "?")
    print(f"  {sid}: rank={rank}, appeared_in={appeared}, source={source}")

# Check if _appeared_in is being stripped by normalize_parsed_data
print("\nChecking raw parse output before normalization...")
raw_sqls = raw.get("sql_stats", [])
print(f"Raw SQL count: {len(raw_sqls)}")
for s in raw_sqls[:3]:
    sid = s.get("sql_id", "?")
    rank = s.get("_elapsed_rank", "?")
    appeared = s.get("_appeared_in", "?")
    source = s.get("_source", "?")
    print(f"  {sid}: rank={rank}, appeared_in={appeared}, source={source}")
