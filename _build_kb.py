"""
Extract and process Oracle Performance Tuning Guide into a structured knowledge base.
Outputs: _oracle_pe_kb.md
"""
import json, re

with open('_oracle_pe_knowledge.json', encoding='utf-8') as f:
    d = json.load(f)

def clean(text):
    text = re.sub(r'Chapter \d+\n.*?\n\d+-\d+\n', '', text)
    text = re.sub(r'See Also:.*?\n', '', text, flags=re.DOTALL)
    text = re.sub(r'ò\s*', '• ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

sections = {}
for k, v in d.items():
    sections[k] = clean(v)

# ─────────────────────────────────────────────────────────────────────────────
# Ch3: Performance Method + Top 10 Mistakes
# ─────────────────────────────────────────────────────────────────────────────
ch3 = sections['ch03_perf_method']
idx_method = ch3.find('Steps in the Oracle Performance Improvement Method')
idx_top10  = ch3.find('Top Ten Mistakes')
idx_emerg  = ch3.find('Emergency Performance')
method_text = ch3[idx_method:idx_top10] if idx_method >= 0 and idx_top10 >= 0 else ''
top10_text  = ch3[idx_top10:idx_emerg]  if idx_top10 >= 0 and idx_emerg >= 0 else ch3[idx_top10:idx_top10+3000]

# ─────────────────────────────────────────────────────────────────────────────
# Ch10: Wait Events Details
# ─────────────────────────────────────────────────────────────────────────────
ch10 = sections['ch10_instance_tuning']

WAIT_EVENTS = [
    'buffer busy waits',
    'db file scattered read',
    'db file sequential read',
    'direct path read',
    'direct path write',
    'enqueue',
    'free buffer waits',
    'latch events',
    'log file parallel write',
    'library cache pin',
    'library cache lock',
    'log buffer space',
    'log file switch',
    'log file sync',
]

wait_event_extracts = {}
for ev in WAIT_EVENTS:
    idx = ch10.find('\n' + ev + '\n')
    if idx < 0:
        idx = ch10.find(ev)
    if idx >= 0:
        # Take up to next event or 3000 chars
        snippet = ch10[idx:idx+3000]
        wait_event_extracts[ev] = snippet.strip()

# ─────────────────────────────────────────────────────────────────────────────
# Ch13: Buffer Cache
# ─────────────────────────────────────────────────────────────────────────────
ch13 = sections['ch13_buffer_cache']
idx_hit = ch13.find('Calculating the Buffer Cache Hit Ratio')
idx_interp = ch13.find('Interpreting the Buffer Cache Hit Ratio')
idx_adv = ch13.find('V$DB_CACHE_ADVICE')
buf_cache_text = ch13[idx_adv:idx_adv+5000] if idx_adv >= 0 else ch13[:5000]

# ─────────────────────────────────────────────────────────────────────────────
# Ch14: Shared Pool
# ─────────────────────────────────────────────────────────────────────────────
ch14 = sections['ch14_shared_pool']
idx_lib = ch14.find('Library Cache Concepts')
idx_sql = ch14.find('SQL Sharing Criteria')
idx_size = ch14.find('Sizing the Shared Pool')
shared_pool_text = ch14[idx_lib:idx_size+3000] if idx_lib >= 0 else ch14[:6000]

# ─────────────────────────────────────────────────────────────────────────────
# Ch16: PGA
# ─────────────────────────────────────────────────────────────────────────────
ch16 = sections['ch16_pga']
idx_pga = ch16.find('Tuning PGA_AGGREGATE_TARGET')
idx_pgastat = ch16.find('V$PGASTAT')
pga_text = ch16[idx_pgastat:idx_pga+4000] if idx_pgastat >= 0 else ch16[:5000]

# ─────────────────────────────────────────────────────────────────────────────
# Write the structured knowledge base
# ─────────────────────────────────────────────────────────────────────────────
out = []
A = out.append

A("# Oracle Performance Engineering Knowledge Base")
A("## Source: Oracle Database Performance Tuning Guide (19c)")
A("")

A("## 1. Oracle Performance Improvement Method (Official Steps)")
A(method_text[:3000])
A("")

A("## 2. Top 10 Mistakes Found in Oracle Systems")
A(top10_text[:3000])
A("")

A("## 3. Wait Event Root Cause Reference")
A("Each wait event description from Oracle's official guide:")
A("")
for ev, text in wait_event_extracts.items():
    A(f"### {ev}")
    A(text[:2500])
    A("")

A("## 4. Buffer Cache Tuning Guide")
A(buf_cache_text[:4000])
A("")

A("## 5. Shared Pool / Library Cache Tuning")
A(shared_pool_text[:4000])
A("")

A("## 6. PGA Tuning")
A(pga_text[:4000])
A("")

# Ch10 Table of Wait Events
idx_table = ch10.find('Table of Wait Events and Potential Causes')
if idx_table >= 0:
    A("## 7. Oracle Official Wait Event → Cause Table")
    A(ch10[idx_table:idx_table+5000])
    A("")

# Ch10 Drill Down
idx_drill = ch10.find('Using Wait Event Statistics to Drill Down')
if idx_drill >= 0:
    A("## 8. Drill-Down Methodology for Bottlenecks")
    A(ch10[idx_drill:idx_drill+4000])
    A("")

# Ch5 Statistics interpretation
ch5 = sections['ch05_measuring']
A("## 9. How to Use Hit Ratios and Wait Statistics")
A(ch5[:5000])
A("")

result = '\n'.join(out)
with open('_oracle_pe_kb.md', 'w', encoding='utf-8') as f:
    f.write(result)

print(f"Knowledge base written: {len(result):,} chars")

# Also print wait events summary
print("\nWait events extracted:")
for ev in wait_event_extracts:
    print(f"  - {ev}: {len(wait_event_extracts[ev])} chars")
