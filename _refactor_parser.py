"""
Refactor _parse_sql_stats in html_parser.py:
- Discover SQL IDs from elapsed-time section ONLY
- Other sections (cpu, gets, reads, executions) enrich existing entries only
- Track which sections each SQL appears in via _appeared_in list
- Add elapsed_rank per SQL for scoring
"""
import sys

path = r"backend\services\html_parser.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

# Find and replace the _parse_sql_stats function's SQL ID discovery loop
old_loop = '''    seen_sql_ids: dict[str, dict[str, Any]] = {}

    for idx, section_kw in enumerate(["elapsed time", "cpu time", "gets", "reads", "executions"]):
        rows = _parse_sql_section(soup, section_kw)
        for row_dict in rows:
            sql_id = _extract_sql_id_from_row(row_dict)
            if not sql_id:
                continue

            if sql_id not in seen_sql_ids:
                seen_sql_ids[sql_id] = {
                    "sql_id": sql_id,
                    "_source": section_kw.replace(" ", "_"),
                }

            _merge_sql_row(seen_sql_ids[sql_id], row_dict, overwrite=(idx == 0))'''

new_loop = '''    seen_sql_ids: dict[str, dict[str, Any]] = {}

    # Phase 1: Discover SQL IDs from elapsed-time section ONLY (source of truth)
    elapsed_rows = _parse_sql_section(soup, "elapsed time")
    for rank, row_dict in enumerate(elapsed_rows, 1):
        sql_id = _extract_sql_id_from_row(row_dict)
        if not sql_id:
            continue
        seen_sql_ids[sql_id] = {
            "sql_id": sql_id,
            "_source": "elapsed_time",
            "_appeared_in": ["elapsed_time"],
            "_elapsed_rank": rank,
        }
        _merge_sql_row(seen_sql_ids[sql_id], row_dict, overwrite=True)

    # Phase 2: Enrich existing entries from other sections (no new SQL IDs added)
    for section_kw in ["cpu time", "gets", "reads", "executions"]:
        section_key = section_kw.replace(" ", "_")
        rows = _parse_sql_section(soup, section_kw)
        for row_dict in rows:
            sql_id = _extract_sql_id_from_row(row_dict)
            if not sql_id or sql_id not in seen_sql_ids:
                continue
            if section_key not in seen_sql_ids[sql_id]["_appeared_in"]:
                seen_sql_ids[sql_id]["_appeared_in"].append(section_key)
            _merge_sql_row(seen_sql_ids[sql_id], row_dict, overwrite=False)'''

if old_loop not in src:
    print("ERROR: Could not find the SQL discovery loop in html_parser.py")
    sys.exit(1)

src = src.replace(old_loop, new_loop)
print("OK: Refactored _parse_sql_stats to elapsed-time-first discovery")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Saved html_parser.py")
