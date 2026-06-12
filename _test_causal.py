import sys; sys.path.insert(0, 'backend')
from services.rca_engine import PATHOLOGY_MAP, _get_pathology

# Verify causal chain for the compare mode events
anomalous_events = {
    'free buffer waits': 58.9,
    'enq: fb - contention': 8.2,
    'buffer busy waits': 6.5,
    'db file sequential read': 2.9,
    'enq: us - contention': 1.2,
    'log buffer space': 0.7,
}

print("=== PATHOLOGY_MAP lookups ===")
for evt, pct in anomalous_events.items():
    p = _get_pathology(evt)
    if p:
        print(f"{evt} ({pct}%): children={p.get('causal_children', [])}, parents={p.get('causal_parents', [])}")
    else:
        print(f"{evt} ({pct}%): NOT IN PATHOLOGY_MAP")

# Simulate the causal chain builder
print("\n=== SIMULATED CAUSAL CHAIN ===")
edges = []
for parent_key, parent_pct in anomalous_events.items():
    if parent_pct < 1.0:
        continue
    pathology = _get_pathology(parent_key)
    for child in pathology.get("causal_children", []):
        child_key = child.lower()
        for anomalous_key in anomalous_events:
            if child_key in anomalous_key or anomalous_key.startswith(child_key[:12]):
                edges.append((parent_key, anomalous_key))
                print(f"  Edge: {parent_key} -> {anomalous_key}")
                break

if edges:
    has_incoming = {child for _, child in edges}
    roots = [k for k in anomalous_events if k not in has_incoming and anomalous_events[k] >= 1.0]
    print(f"\nRoots: {roots}")
    print("Causal chain confirmed!")
else:
    print("\nNo edges found — would report 'Isolated anomalous events'")
