import sys
sys.path.insert(0, 'backend')
from services.awr_intelligence import AWRFinding, _generate_fix_statement

cases = [
    AWRFinding(id='wait_latch_library_cache', severity='CRITICAL', category='Latch',
               title='latch: library cache', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['latch','parse']),
    AWRFinding(id='sql_cpu_abc123', severity='CRITICAL', category='SQL',
               title='[WORSE] SQL abc123', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['sql','cpu'], sql_ids=['abc123']),
    AWRFinding(id='wait_log_file_sync', severity='WARNING', category='Redo',
               title='log file sync', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['redo','commit','io']),
    AWRFinding(id='wait_latch_cache_buffers_chains', severity='CRITICAL', category='Latch',
               title='[NEW] latch: cache buffers chains', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['latch','hot_block','buffer_cache']),
    AWRFinding(id='sql_gets_xyz456', severity='WARNING', category='SQL',
               title='SQL xyz456', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['sql','buffer'], sql_ids=['xyz456']),
    AWRFinding(id='enq_tx', severity='CRITICAL', category='Locking',
               title='enq: TX - row lock contention', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['lock','blocking','tx']),
    AWRFinding(id='ts_io_data', severity='CRITICAL', category='I/O',
               title='Slow I/O: Tablespace DATA', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['io','tablespace']),
    AWRFinding(id='cpu_saturation', severity='CRITICAL', category='CPU',
               title='CPU Saturation', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['cpu']),
    AWRFinding(id='latch_unknown_widget', severity='WARNING', category='Latch',
               title='latch: widget cache latch', headline='h', evidence=[], root_cause='r', fix='f',
               tags=['latch']),
]

all_ok = True
for c in cases:
    fd = _generate_fix_statement(c)
    assert len(fd) == 11, 'Wrong key count: %s' % list(fd.keys())
    rct = fd['root_cause_type']
    conf = fd['confidence']
    print('%-45s rct=%-22s conf=%s' % (c.id[:45], rct, conf))

    # Rule: no generic shared_pool or bind_var advice on hot-block latch
    if 'cache_buffers_chains' in c.id:
        if 'SHARED_POOL_SIZE' in fd['fix_statement']:
            print('  FAIL: Generic SHARED_POOL_SIZE on cache buffers chains!')
            all_ok = False
        if 'bind variable' in fd['fix_statement'].lower():
            print('  FAIL: bind variable advice on cache buffers chains!')
            all_ok = False
        found_xbh = any('x$bh' in (fd.get(k) or '').lower() for k in ['action_1','action_2','action_3'])
        if not found_xbh:
            print('  FAIL: Missing x$bh hot-block check on cache buffers chains!')
            all_ok = False

    # Rule: unknown latch → investigation-first
    if 'widget' in c.id:
        if 'targeted' not in fd['fix_statement'].lower() and 'investigation' not in fd['fix_statement'].lower():
            print('  FAIL: Unknown latch should say "targeted investigation"!')
            all_ok = False

    # Rule: SQL regression → must reference sql_id
    if c.id.startswith('sql_') and c.sql_ids:
        if c.sql_ids[0] not in fd['fix_statement'] and c.sql_ids[0] not in fd['action_1']:
            print('  WARN: SQL ID not referenced in fix for %s' % c.id)

print()
print('All assertions passed' if all_ok else 'SOME ASSERTIONS FAILED')
