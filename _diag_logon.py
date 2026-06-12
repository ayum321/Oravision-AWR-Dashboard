"""Diagnostic: test logon metric extraction from real AWR files — including normalization."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from backend.services.html_parser import parse_awr_html, normalize_parsed_data

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"

# Find 2 AWR files to test
import glob
files = glob.glob(os.path.join(AWR_DIR, "**/*.html"), recursive=True)[:3]

for f in files:
    print(f"\n{'='*80}")
    print(f"FILE: {os.path.basename(f)}")
    print('='*80)
    with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
        html = fh.read()
    
    raw = parse_awr_html(html)
    
    print(f"\nRAW EXTRACTED:")
    print(f"  logons_cumulative_total = {raw.get('logons_cumulative_total', 'NOT SET')}")
    print(f"  logons_current_begin    = {raw.get('logons_current_begin', 'NOT SET')}")
    print(f"  logons_current_end      = {raw.get('logons_current_end', 'NOT SET')}")
    
    # Normalize through Pydantic (this is where it was lost!)
    model = normalize_parsed_data(raw)
    data_dict = model.model_dump()
    
    print(f"\nAFTER NORMALIZE (Pydantic round-trip):")
    print(f"  logons_cumulative_total = {data_dict.get('logons_cumulative_total', 'NOT SET')}")
    print(f"  logons_current_begin    = {data_dict.get('logons_current_begin', 'NOT SET')}")
    print(f"  logons_current_end      = {data_dict.get('logons_current_end', 'NOT SET')}")
    
    # Simulate the fix in _parse_and_store
    for _lf in ("logons_cumulative_total", "logons_current_begin", "logons_current_end"):
        if raw.get(_lf) is not None and data_dict.get(_lf) is None:
            data_dict[_lf] = raw[_lf]
    
    print(f"\nFINAL (after fallback):")
    print(f"  logons_cumulative_total = {data_dict.get('logons_cumulative_total', 'NOT SET')}")
    print(f"  logons_current_begin    = {data_dict.get('logons_current_begin', 'NOT SET')}")
    print(f"  logons_current_end      = {data_dict.get('logons_current_end', 'NOT SET')}")
