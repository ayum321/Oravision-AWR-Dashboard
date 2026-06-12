"""Fix all ?% (broken Δ%) occurrences in index.html"""
import sys

path = r"backend\templates\index.html"
content = open(path, encoding='utf-8').read()
original = content

replacements = [
    # Sort button for efficiency table delta
    (
        'id="eff-sort-del" style="font-size:8px;padding:3px 9px;background:transparent;color:#475569;border:none;border-left:1px solid #1e293b;cursor:pointer">?%</button>',
        'id="eff-sort-del" style="font-size:8px;padding:3px 9px;background:transparent;color:#475569;border:none;border-left:1px solid #1e293b;cursor:pointer">\u0394%</button>',
    ),
    # Efficiency table column header
    (
        'onclick="sortEffTable(\'delta\')">?% ?</th>',
        'onclick="sortEffTable(\'delta\')">\u0394% \u21c5</th>',
    ),
    # SQL mini table header
    (
        '<th ${TH}>?%</th>',
        '<th ${TH}>\u0394%</th>',
    ),
    # Sort buttons array label
    (
        "['Elapsed ?%','epeD']",
        "['Elapsed \u0394%','epeD']",
    ),
    # New SQL table header Elapsed delta
    (
        '<th style="color:#475569">Elapsed ?%</th>',
        '<th style="color:#475569">Elapsed \u0394%</th>',
    ),
    # New SQL table header Execs delta
    (
        '<th style="color:#475569">Execs ?%</th>',
        '<th style="color:#475569">Execs \u0394%</th>',
    ),
    # Compare table header
    (
        '><th>?%</th><th>${esc(lbl2)} %DB</th>',
        '><th>\u0394%</th><th>${esc(lbl2)} %DB</th>',
    ),
]

fixed = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        fixed += 1
        print(f"Fixed: {repr(old[:60])}")
    else:
        print(f"NOT FOUND: {repr(old[:60])}")

if fixed > 0:
    open(path, 'w', encoding='utf-8').write(content)
    print(f"\nSaved {fixed}/{len(replacements)} fixes to {path}")
else:
    print("Nothing changed")
