"""
Fix field names: parser uses _source/_appeared_in/_elapsed_rank but
Pydantic model needs source_section/appeared_in/elapsed_rank.
Update parser dict keys to match model.
Then update frontend to read the correct field names.
"""
import sys

# Fix 1: Parser field names
path = r"backend\services\html_parser.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

replacements = [
    ('"_source": "elapsed_time"', '"source_section": "elapsed_time"'),
    ('"_appeared_in": ["elapsed_time"]', '"appeared_in": ["elapsed_time"]'),
    ('"_elapsed_rank": rank', '"elapsed_rank": rank'),
    ('seen_sql_ids[sql_id]["_appeared_in"]', 'seen_sql_ids[sql_id]["appeared_in"]'),
]
for old, new in replacements:
    if old in src:
        src = src.replace(old, new)
        print(f"  Parser: {old[:40]}... -> {new[:40]}...")
    else:
        print(f"  WARN: Not found in parser: {old[:50]}")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Parser updated.\n")

# Fix 2: Frontend field names in buildEntry
path2 = r"backend\templates\index.html"
with open(path2, "r", encoding="utf-8") as f:
    src2 = f.read()

fe_replacements = [
    ("s._appeared_in || ['elapsed_time']", "s.appeared_in || ['elapsed_time']"),
    ("s._elapsed_rank || 999", "s.elapsed_rank || 999"),
    ("s._source || 'elapsed_time'", "s.source_section || 'elapsed_time'"),
]
for old, new in fe_replacements:
    if old in src2:
        src2 = src2.replace(old, new)
        print(f"  Frontend: {old[:40]}... -> {new[:40]}...")
    else:
        print(f"  WARN: Not found in frontend: {old[:50]}")

with open(path2, "w", encoding="utf-8") as f:
    f.write(src2)
print("Frontend updated.")
