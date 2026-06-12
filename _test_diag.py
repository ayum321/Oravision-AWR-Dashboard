import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find WAIT_DIAG_ENGINE
idx = content.find('const WAIT_DIAG_ENGINE')
end = content.find('];', idx)
engine_block = content[idx:end+2]

# Extract events
events = re.findall(r"event:\s*'([^']+)'", engine_block)
print(f"WAIT_DIAG_ENGINE has {len(events)} events:")

for evt in events:
    evt_idx = engine_block.find(f"event: '{evt}'")
    # Find the queries array for this event
    q_start = engine_block.find('queries:', evt_idx)
    # Find next event or end of block
    next_evt = engine_block.find("event: '", evt_idx + 10)
    if next_evt == -1:
        q_section = engine_block[q_start:end]
    else:
        q_section = engine_block[q_start:next_evt]
    
    steps = re.findall(r"step:\s*(\d+)", q_section)
    ids = re.findall(r"id:\s*'([^']+)'", q_section)
    has_index = 'INDEX_HEALTH' in q_section
    marker = ' <-- HAS INDEX_HEALTH' if has_index else ''
    print(f"  {evt}: {len(steps)} steps, IDs={ids}{marker}")

# Now verify getDiagCatalogEntry logic
print("\n--- getDiagCatalogEntry function check ---")
fn_idx = content.find('function getDiagCatalogEntry')
fn_block = content[fn_idx:fn_idx+2000]
# Check it matches on the bad[0] event
has_bad_match = 'bad' in fn_block and 'event_name' in fn_block
print(f"Matches on bad waitEvents[0].event_name: {has_bad_match}")

# Check Block 5c dedup logic  
b5c_idx = content.find('Block 5c: EXTENDED DIAGNOSTIC')
b5c_block = content[b5c_idx:b5c_idx+500]
has_dedup = 'q.step > 1' in b5c_block
print(f"\nBlock 5c skips Step 1 (dedup): {has_dedup}")

# Check compare mode dedup
cmp_idx = content.find('Extended Diagnostic Steps (Compare Mode')
cmp_block = content[cmp_idx:cmp_idx+500]
has_dedup_cmp = 'q.step > 1' in cmp_block
print(f"Compare mode skips Step 1 (dedup): {has_dedup_cmp}")
