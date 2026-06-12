import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('backend/templates/index.html','r',encoding='utf-8') as f:
    lines = f.readlines()

patterns = [
    (r'(?i)\bIncrease\b.*(?:PGA_AGGREGATE_TARGET|pga_aggregate_target)', 'INC_PGA'),
    (r'(?i)\bIncrease\b.*(?:DB_WRITER_PROCESSES|db_writer_processes)', 'INC_DBWRITER'),
    (r'(?i)\bIncrease\b.*(?:LOG_BUFFER|log_buffer)\b', 'INC_LOGBUF'),
    (r'(?i)\bIncrease\b.*(?:SHARED_POOL_SIZE|shared_pool_size)', 'INC_SHAREDPOOL'),
    (r'(?i)\bIncrease\b.*(?:DB_CACHE_SIZE|db_cache_size)', 'INC_DBCACHE'),
    (r'(?i)\bIncrease\b.*(?:UNDO_RETENTION|undo_retention|UNDO_TABLESPACE)', 'INC_UNDO'),
    (r'(?i)\bIncrease\b.*redo log size', 'INC_REDOLOG'),
    (r'(?i)\bIncrease\b.*sequence.*CACHE', 'INC_SEQCACHE'),
    (r'(?i)ALTER TABLE.*ALLOCATE EXTENT', 'ALTER_ALLOCATE'),
    (r'(?i)ALTER INDEX.*REBUILD', 'ALTER_REBUILD'),
    (r'(?i)ALTER DATABASE ADD LOGFILE', 'ALTER_LOGFILE'),
    (r'(?i)ALTER SYSTEM SET log_archive_max', 'ALTER_LGWR'),
    (r'(?i)ALTER SEQUENCE.*CACHE\s+\d', 'ALTER_SEQ'),
    (r"(?i)fixAction.*\bIncrease\b", 'FIXACTION_INC'),
    (r"(?i)tldr.*\bIncrease\b", 'TLDR_INC'),
]
hits = {}
for pat, label in patterns:
    for i, line in enumerate(lines, 1):
        if re.search(pat, line):
            hits.setdefault(label, []).append((i, line.strip()[:180]))

total = sum(len(v) for v in hits.values())
print(f'Total remaining hits: {total}')
for label, items in hits.items():
    print(f'\n=== {label} ({len(items)} hits) ===')
    for lineno, text in items[:5]:
        print(f'  L{lineno}: {text}')
