import re, sys

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Simple grep-based approach — find all event keys in WAIT_DIAG_ENGINE
# Look for lines like:  'db file sequential read': {
idx_start = content.find('const WAIT_DIAG_ENGINE')
idx_end = content.find('function getDiagCatalogEntry', idx_start)
block = content[idx_start:idx_end]

# Find event names (top-level keys at 2-space indent)
event_lines = re.findall(r"^  '([^']+)':\s*\{", block, re.MULTILINE)
print(f"WAIT_DIAG_ENGINE: {len(event_lines)} events")

# For each event, count query IDs in the section  
for evt in event_lines:
    # Find start of this event section
    start = block.find(f"'{evt}': {{")
    # Find all id: 'X' lines from start until next event or end
    rest = block[start:]
    # Find next event definition (2-space indent + single quote)
    next_match = re.search(r"\n  '[^']+':\s*\{", rest[10:])
    if next_match:
        section = rest[:next_match.start() + 10]
    else:
        section = rest
    
    ids = re.findall(r"id:\s*'([^']+)'", section)
    has_ih = 'INDEX_HEALTH' in section
    flag = ' *** INDEX_HEALTH ***' if has_ih else ''
    print(f"  {evt}: {len(ids)} steps -> {ids}{flag}")

# Verify dedup logic
print("\n=== DEDUP CHECK ===")
b5c_idx = content.find('Block 5c: EXTENDED DIAGNOSTIC')
b5c_near = content[b5c_idx:b5c_idx+1500]
print(f"Block 5c has 'q.step > 1': {'q.step > 1' in b5c_near}")
print(f"Block 5c has '_availableQueries': {'_availableQueries' in b5c_near}")

cmp_idx = content.find('Compare Mode')  
cmp_near = content[cmp_idx:cmp_idx+1500]
print(f"Compare mode has 'q.step > 1': {'q.step > 1' in cmp_near}")
print(f"Compare mode has '_availableQueries': {'_availableQueries' in cmp_near}")

# Verify scoring does NOT give Step 1 boost anymore
print("\n=== SCORE FUNCTION CHECK ===")
# Find the scored = ... line in Block 5c
scored_line_idx = content.find('_availableQueries.map', b5c_idx)
if scored_line_idx > 0:
    scored_line = content[scored_line_idx:scored_line_idx+200]
    has_step1_boost = 'step === 1' in scored_line or 'step == 1' in scored_line
    print(f"Single: scored uses _availableQueries: True")
    print(f"Single: Step 1 boost still present: {has_step1_boost}")
else:
    print("WARNING: _availableQueries.map not found in Block 5c!")
    # Check what IS there
    scored_alt = content.find('diag.queries.map', b5c_idx, b5c_idx+5000)
    if scored_alt > 0:
        print("  Found diag.queries.map instead - OLD CODE STILL THERE!")
    else:
        print("  No .map call found nearby")

sys.exit(0)
