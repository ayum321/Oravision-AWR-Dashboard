import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# WAIT_DIAG_ENGINE is an object literal, find its boundaries
idx = content.find('const WAIT_DIAG_ENGINE')
# It's a large object ending with }; - find by counting braces
start_brace = content.find('{', idx)
depth = 0
end_brace = start_brace
for i in range(start_brace, min(start_brace + 50000, len(content))):
    if content[i] == '{':
        depth += 1
    elif content[i] == '}':
        depth -= 1
        if depth == 0:
            end_brace = i
            break

engine_block = content[start_brace:end_brace+1]
print(f"WAIT_DIAG_ENGINE block: {len(engine_block)} chars")

# Find all top-level event keys (pattern: '  'event_name': {')
events = re.findall(r"  '([^']+)':\s*\{", engine_block)
print(f"Events found: {len(events)}")

for evt in events:
    # Find section for this event
    pat = f"'{evt}':"
    evt_idx = engine_block.find(pat)
    # Find queries for this event - look for id: fields
    # Section ends at next top-level event or end
    remaining = engine_block[evt_idx:]
    # Find next top-level event (2-space indent followed by quote)
    next_evt = re.search(r"\n  '[^']+':\s*\{", remaining[len(pat):])
    if next_evt:
        section = remaining[:next_evt.start() + len(pat)]
    else:
        section = remaining
    
    ids = re.findall(r"id:\s*'([^']+)'", section)
    steps = re.findall(r"step:\s*(\d+)", section)
    has_index = 'INDEX_HEALTH' in section
    marker = ' <-- INDEX_HEALTH' if has_index else ''
    print(f"  {evt}: {len(ids)} queries, IDs={ids}{marker}")

# Check dedup in Block 5c
print("\n--- Deduplication Check ---")
b5c_start = content.find('Block 5c: EXTENDED DIAGNOSTIC')
b5c_section = content[b5c_start:b5c_start+2000]
print(f"Block 5c has 'step > 1' filter: {'q.step > 1' in b5c_section}")
print(f"Block 5c has '_availableQueries': {'_availableQueries' in b5c_section}")

# Check compare-mode dedup
cmp_start = content.find('Extended Diagnostic Steps (Compare Mode')
cmp_section = content[cmp_start:cmp_start+2000]
print(f"Compare mode has 'step > 1' filter: {'q.step > 1' in cmp_section}")
print(f"Compare mode has '_availableQueries': {'_availableQueries' in cmp_section}")

# Check the scoring function excludes Step 1 boost
print("\n--- Score Function Check ---")
score_single = content.find('_scoreDiagQuery')
score_block = content[score_single:score_single+1500]
has_step1_boost = 'q.step === 1' in score_block or 'step === 1 ? 1' in score_block
print(f"Single-mode scorer still has Step 1 boost: {has_step1_boost}")

score_compare = content.find('_scoreDiagC')
score_block2 = content[score_compare:score_compare+1500]
has_step1_boost2 = 'q.step === 1' in score_block2 or 'step === 1 ? 1' in score_block2
print(f"Compare-mode scorer still has Step 1 boost: {has_step1_boost2}")
