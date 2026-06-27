#!/usr/bin/env python3
"""
Smoke test for Wait Event Catalog hardening.
Verifies that new canonical wait events are defined in index.html.
"""
import sys
import os

HTML_FILE = os.path.join(
    os.path.dirname(__file__),
    '..',
    'backend',
    'templates',
    'index.html'
)

# List of new Tier-1 events that should be in the canonical catalog
NEW_CANONICAL_EVENTS = [
    'SQL*Net message from client',
    'SQL*Net message to client',
    'enq: ST - space transaction',
    'enq: RO - fast object reuse',
    'control file parallel write',
    'control file sequential read',
    'log file switch completion',
    'gc cr request',
    'gc cr grant 2-way',
    'gc current block 2-way',
    'gc cr grant congested',
    'gc current block congested',
    'gc cr block busy',
    'PX Deq: Execute Reply',
    'PX Deq: Parse Reply',
    'PX Deq: Table Q Normal',
    'library cache load lock',
    'latch: session allocation',
    'enq: CI - contention',
    'latch: object queue header operation',
]

# Events not yet in catalog (but valuable to add in future)
OPTIONAL_EVENTS = [
    'control file parallel read',  # Oracle doesn't have separate parallel read
    'gc current request',            # Not a real Oracle event
]

def read_html():
    """Read the HTML file."""
    try:
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"✗ FAILED to read {HTML_FILE}: {e}")
        sys.exit(1)

def test_events_present():
    """Verify all new events are in the catalog."""
    print("\n" + "="*70)
    print("TEST: New Events Present in Canonical Catalog")
    print("="*70 + "\n")
    
    html = read_html()
    
    if 'const WAIT_EVENT_CATALOG = {' not in html:
        print("✗ Could not find WAIT_EVENT_CATALOG")
        return False
    
    all_present = True
    for event in NEW_CANONICAL_EVENTS:
        search_str = f"'{event}':"
        if search_str in html:
            print(f"  ✓ {event}")
        else:
            print(f"  ✗ {event} NOT FOUND")
            all_present = False
    
    return all_present

def test_no_duplicates():
    """Check for duplicate keys using PowerShell grep."""
    print("\n" + "="*70)
    print("TEST: No Duplicate Keys in Catalog")
    print("="*70 + "\n")
    
    html = read_html()
    
    # Find catalog section
    start_idx = html.find('const WAIT_EVENT_CATALOG = {')
    if start_idx < 0:
        print("✗ Could not find WAIT_EVENT_CATALOG")
        return False
    
    # Find end of catalog (before the guard function)
    end_idx = html.find('function _warnDuplicateWaitCatalogKeysFromSource', start_idx)
    if end_idx < 0:
        end_idx = len(html)
    
    catalog_section = html[start_idx:end_idx]
    
    # Simple duplicate check: extract event names
    import re
    events = re.findall(r"'([^']+)':", catalog_section)
    
    print(f"Total keys found: {len(events)}\n")
    
    seen = set()
    duplicates = []
    for ev in events:
        if ev in seen:
            if ev not in duplicates:
                duplicates.append(ev)
        seen.add(ev)
    
    if duplicates:
        for dup in duplicates:
            print(f"  ✗ DUPLICATE: {dup}")
        print(f"\n✗ Found {len(duplicates)} duplicate(s)")
        return False
    else:
        print("  ✓ No duplicates detected")
        return True

def test_guard_function():
    """Check for the runtime guard function."""
    print("\n" + "="*70)
    print("TEST: Runtime Duplicate-Key Guard")
    print("="*70 + "\n")
    
    html = read_html()
    
    if '_warnDuplicateWaitCatalogKeysFromSource' in html:
        print("  ✓ Guard function found")
        if 'console.warn' in html and 'duplicate' in html.lower():
            print("  ✓ Guard includes console.warn for duplicates")
            return True
        return True
    else:
        print("  ✗ Guard function not found")
        return False

if __name__ == '__main__':
    try:
        r1 = test_events_present()
        r2 = test_no_duplicates()
        r3 = test_guard_function()
        
        print("\n" + "="*70)
        if all([r1, r2, r3]):
            print("✓ SMOKE TEST PASSED: Catalog hardening verified")
            print("="*70 + "\n")
            sys.exit(0)
        else:
            print("✗ SMOKE TEST FAILED")
            print("="*70 + "\n")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
