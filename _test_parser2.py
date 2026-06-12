"""Direct test of parser output with correct field names."""
import sys
sys.path.insert(0, "backend")

# Force reimport
import importlib
from services import html_parser
importlib.reload(html_parser)

from services.html_parser import parse_awr_html, normalize_parsed_data

with open(r"C:\Users\1039081\Downloads\BAD.html", "r", encoding="utf-8", errors="replace") as f:
    raw = parse_awr_html(f.read())

# Raw output (before normalization)
raw_sqls = raw.get("sql_stats", [])
print(f"Raw SQL count: {len(raw_sqls)}")
for s in raw_sqls[:5]:
    sid = s.get("sql_id", "?")
    rank = s.get("elapsed_rank", "?")
    appeared = s.get("appeared_in", "?")
    source = s.get("source_section", "?")
    print(f"  {sid}: rank={rank}, appeared_in={appeared}, source={source}")

# Normalized output (through Pydantic)
d = normalize_parsed_data(raw).model_dump()
sqls = d.get("sql_stats", [])
print(f"\nNormalized SQL count: {len(sqls)}")
for s in sqls[:5]:
    sid = s.get("sql_id", "?")
    rank = s.get("elapsed_rank", "?")
    appeared = s.get("appeared_in", "?")
    source = s.get("source_section", "?")
    print(f"  {sid}: rank={rank}, appeared_in={appeared}, source={source}")
