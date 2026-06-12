import sys; sys.path.insert(0, 'backend')
from services.rca_engine import PATHOLOGY_MAP

for k in ['free buffer waits', 'buffer busy waits', 'enq: fb - contention', 'enq: hw - contention', 'db file sequential read']:
    e = PATHOLOGY_MAP.get(k, {})
    if e:
        print(f'{k}:')
        print(f'  category: {e.get("category","?")}')
        print(f'  causal_parents: {e.get("causal_parents",[])}')
        print(f'  causal_children: {e.get("causal_children",[])}')
    else:
        print(f'{k}: NOT FOUND')
    print()

print('All PATHOLOGY_MAP keys:')
for k in sorted(PATHOLOGY_MAP.keys()):
    e = PATHOLOGY_MAP[k]
    p = e.get('causal_parents', [])
    c = e.get('causal_children', [])
    print(f'  {k}: parents={p}, children={c}')
