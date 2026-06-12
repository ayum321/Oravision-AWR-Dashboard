import re, requests

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    c = f.read()

print("=== STRUCTURAL INTEGRITY ===")
print(f"Braces: {c.count('{')}/{c.count('}')}", "OK" if c.count('{')==c.count('}') else "MISMATCH")
print(f"Divs: {c.count('<div')}/{c.count('</div>')}", "OK" if c.count('<div')==c.count('</div>') else "MISMATCH")
print(f"Lines: {len(c.splitlines())}")

print("\n=== ENCODING CHECK ===")
# Check for remaining mojibake
mojibake_count = 0
for i, line in enumerate(c.splitlines()):
    # Look for the specific mojibake pattern
    if '\u00f0\u0178' in line or '\u00c3\u00b0' in line:
        mojibake_count += 1
        print(f"  MOJIBAKE L{i+1}: {repr(line.strip()[:60])}")
print(f"Mojibake remaining: {mojibake_count}")

print("\n=== FEATURE CHECKS ===")
checks = [
    ("Duration field", "Duration:</span>" in c),
    ("Window diff banner", "Windows differ" in c),
    ("Bottleneck descriptor", "topEventDescriptor" in c),
    ("Delta bottleneck override", "maxDeltaClass" in c),
    ("LOAD_PROFILE_PATTERNS", "LOAD_PROFILE_PATTERNS" in c),
    ("DML_SURGE", "DML_SURGE" in c),
    ("Driver cards (RCA)", "STRUCTURED DRIVER CARDS" in c),
    ("SQL tabs layout", "sql-tab-pane" in c),
    ("sql-pane-common", "sql-pane-common" in c),
    ("sql-pane-new", "sql-pane-new" in c),
    ("sql-pane-gone", "sql-pane-gone" in c),
    ("No duplicate Txn panel", c.count("PANEL 1b: Transactions/sec") == 1),
    ("No old Attribution", "SQL Attribution Analysis" not in c or c.count("SQL Attribution Analysis") == 0),
    ("No old ADDM Corroboration section", "ADDM Corroboration" not in c),
    ("No old Verification Query section", "Verification Query from catalog" not in c),
]
for name, ok in checks:
    print(f"  {name}: {'OK' if ok else 'FAIL'}")

print("\n=== SCRIPT SYNTAX ===")
scripts = re.findall(r'<script[^>]*>(.*?)</script>', c, re.DOTALL)
all_ok = True
for i, s in enumerate(scripts):
    o = s.count('{')
    cl = s.count('}')
    if abs(o - cl) > 2:
        print(f"  Script {i}: MISMATCH open={o} close={cl}")
        all_ok = False
print("All scripts balanced" if all_ok else "SCRIPT ISSUES DETECTED")

print("\n=== SERVER CHECK ===")
try:
    r = requests.get('http://localhost:8000/', timeout=5)
    print(f"Server: {r.status_code}")
except:
    print("Server: UNREACHABLE")
