"""Test that SQL text is mapped to the correct SQL ID — not misaligned."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.html_parser import _parse_sql_stats
from bs4 import BeautifulSoup

# =============================================================================
# TEST 1: Normal AWR — "Complete List of SQL Text" with proper 2-column table
# =============================================================================
html_normal = '''<html><body>
<table summary="sql ordered by elapsed time">
<tr><th>SQL Id</th><th>Elapsed Time (s)</th><th>Executions</th><th>Elapsed per Exec (s)</th><th>%Total</th><th>SQL Text</th></tr>
<tr><td>atd87px4a8k25</td><td>982.5</td><td>100</td><td>9.825</td><td>5.2</td><td>SELECT /* inline atd */</td></tr>
<tr><td>atwuyuvqkf27w</td><td>237.8</td><td>50</td><td>4.756</td><td>2.1</td><td>SELECT /* inline atw */</td></tr>
<tr><td>bcd12345ef678</td><td>100.0</td><td>200</td><td>0.5</td><td>1.0</td><td>INSERT INTO orders</td></tr>
</table>

<h3>Complete List of SQL Text</h3>
<table>
<tr><th>SQL Id</th><th>SQL Text</th></tr>
<tr><td><a name="atd87px4a8k25">atd87px4a8k25</a></td><td>SELECT /* full text for atd87px4a8k25 */ col1, col2 FROM my_table WHERE id = :b1</td></tr>
<tr><td><a name="atwuyuvqkf27w">atwuyuvqkf27w</a></td><td>SELECT /* OPT_PARAM('_fix_control' '16391176:1') */ GROUP_TYPE, BUCKET_START FROM tm_buckets</td></tr>
<tr><td><a name="bcd12345ef678">bcd12345ef678</a></td><td>INSERT INTO orders (id, name) VALUES (:1, :2)</td></tr>
</table>
</body></html>'''

soup1 = BeautifulSoup(html_normal, 'html.parser')
entries1, map1 = _parse_sql_stats(soup1)
entry_by_id1 = {e['sql_id']: e for e in entries1}

print("=== TEST 1: Normal 2-column table ===")
for sid in ['atd87px4a8k25', 'atwuyuvqkf27w', 'bcd12345ef678']:
    e = entry_by_id1[sid]
    print(f"  {sid}: text={e.get('sql_text','')[:60]}")
    print(f"    verified={e.get('text_verified')}, tables={e.get('tables_referenced')}")

assert 'my_table' in entry_by_id1['atd87px4a8k25']['sql_text'], "FAIL: atd87px should have my_table text"
assert 'OPT_PARAM' not in entry_by_id1['atd87px4a8k25']['sql_text'], "FAIL: atd87px has wrong text from atwuyuv!"
assert 'OPT_PARAM' in entry_by_id1['atwuyuvqkf27w']['sql_text'], "FAIL: atwuyuv missing its OPT_PARAM text"
assert 'orders' in entry_by_id1['bcd12345ef678']['sql_text'], "FAIL: bcd123 missing orders text"
print("  PASSED")

# =============================================================================
# TEST 2: Text starts with wrong SQL ID (the exact bug from screenshot)
# The parser should detect and correct this
# =============================================================================
html_wrong_prefix = '''<html><body>
<table summary="sql ordered by elapsed time">
<tr><th>SQL Id</th><th>Elapsed Time (s)</th><th>Executions</th><th>Elapsed per Exec (s)</th><th>%Total</th><th>SQL Text</th></tr>
<tr><td>atd87px4a8k25</td><td>982.5</td><td>100</td><td>9.825</td><td>5.2</td><td>atwuyuvqkf27w SELECT /* OPT wrong mapping */</td></tr>
<tr><td>atwuyuvqkf27w</td><td>237.8</td><td>50</td><td>4.756</td><td>2.1</td><td>SELECT /* inline correct */</td></tr>
</table>
</body></html>'''

soup2 = BeautifulSoup(html_wrong_prefix, 'html.parser')
entries2, map2 = _parse_sql_stats(soup2)
entry_by_id2 = {e['sql_id']: e for e in entries2}

print("\n=== TEST 2: Inline text starts with wrong SQL ID ===")
for sid in ['atd87px4a8k25', 'atwuyuvqkf27w']:
    e = entry_by_id2[sid]
    print(f"  {sid}: text={e.get('sql_text','')[:60]}")

# atd87px4a8k25's inline text starts with 'atwuyuvqkf27w' — should be stripped/discarded
atd_text = entry_by_id2['atd87px4a8k25'].get('sql_text', '')
assert not atd_text.startswith('atwuyuvqkf27w'), f"FAIL: atd87px still has wrong SQL ID prefix! text={atd_text[:40]}"
print("  PASSED — wrong SQL ID prefix detected and stripped")

# =============================================================================
# TEST 3: SQL ID validation — non-SQL-ID values should not be used as keys
# =============================================================================
html_bad_keys = '''<html><body>
<table summary="sql ordered by elapsed time">
<tr><th>SQL Id</th><th>Elapsed Time (s)</th><th>Executions</th><th>Elapsed per Exec (s)</th><th>%Total</th><th>SQL Text</th></tr>
<tr><td>abc123def4567</td><td>500.0</td><td>100</td><td>5.0</td><td>3.0</td><td>SELECT 1</td></tr>
</table>
<h3>Complete List of SQL Text</h3>
<table>
<tr><th>SQL Id</th><th>SQL Text</th></tr>
<tr><td>982.5</td><td>this is not a real sql id row</td></tr>
<tr><td>abc123def4567</td><td>SELECT /* real sql text */ FROM real_table WHERE x=1</td></tr>
</table>
</body></html>'''

soup3 = BeautifulSoup(html_bad_keys, 'html.parser')
entries3, map3 = _parse_sql_stats(soup3)
entry_by_id3 = {e['sql_id']: e for e in entries3}

print("\n=== TEST 3: Non-SQL-ID values rejected as keys ===")
assert '982.5' not in map3, f"FAIL: '982.5' accepted as SQL ID key!"
assert 'abc123def4567' in entry_by_id3, "FAIL: real SQL ID missing"
assert 'real_table' in entry_by_id3['abc123def4567'].get('sql_text', ''), "FAIL: real SQL missing its text"
print("  PASSED — numeric values rejected, real SQL IDs accepted")

# =============================================================================
# TEST 4: Rowspan handling — text in same-row column 2 (not next row)
# =============================================================================
html_same_row = '''<html><body>
<table summary="sql ordered by elapsed time">
<tr><th>SQL Id</th><th>Elapsed Time (s)</th><th>Executions</th><th>Elapsed per Exec (s)</th><th>%Total</th><th>SQL Text</th></tr>
<tr><td>xyz789abc1234</td><td>300.0</td><td>80</td><td>3.75</td><td>2.0</td><td>SELECT inline xyz</td></tr>
</table>
<h3>Complete List of SQL Text</h3>
<table>
<tr><th>SQL Id</th><th>SQL Text</th></tr>
<tr><td><a name="xyz789abc1234">xyz789abc1234</a></td><td>SELECT /* full xyz text */ a, b, c FROM xyz_table JOIN other_table ON xyz_table.id = other_table.fk</td></tr>
</table>
</body></html>'''

soup4 = BeautifulSoup(html_same_row, 'html.parser')
entries4, map4 = _parse_sql_stats(soup4)
entry_by_id4 = {e['sql_id']: e for e in entries4}

print("\n=== TEST 4: Same-row text extraction ===")
e4 = entry_by_id4['xyz789abc1234']
print(f"  xyz789abc1234: text={e4.get('sql_text','')[:80]}")
print(f"    tables={e4.get('tables_referenced')}")
assert 'XYZ_TABLE' in str(e4.get('tables_referenced', [])), "FAIL: tables not extracted from same-row text"
assert 'full xyz text' in e4.get('sql_text', ''), "FAIL: full text not picked up from same row"
print("  PASSED — same-row extraction works")

print("\n" + "="*50)
print("ALL SQL TEXT MAPPING TESTS PASSED")
print("="*50)
