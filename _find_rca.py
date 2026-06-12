with open('backend/templates/index.html','r',encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if "rca-content" in line and "innerHTML" in line:
        print(f"L{i+1}: rca-content rendering")
    if 'function renderRCA' in line or 'function renderComparisonRCA' in line:
        print(f"L{i+1}: {line.strip()[:80]}")
    if 'compNarrative' in line and ('generateComparison' in line or 'Verdict' in line):
        print(f"L{i+1}: {line.strip()[:80]}")
    if 'generateVerdictNarrative' in line:
        print(f"L{i+1}: {line.strip()[:80]}")
    if 'Comparison Verdict' in line:
        print(f"L{i+1}: {line.strip()[:80]}")
    if 'function renderRCA' in line.lower() or 'function renderrca' in line.lower():
        print(f"L{i+1}: {line.strip()[:80]}")
