#!/usr/bin/env python3
"""
Final icon cleanups for backend/templates/index.html.
Fixes remaining ?? and ? placeholder characters.
"""
import re, os

FILE = os.path.join(os.path.dirname(__file__), 'backend', 'templates', 'index.html')
with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

original_len = len(content)
fixes = 0

def fix(old, new, label=''):
    global content, fixes
    if old in content:
        content = content.replace(old, new)
        fixes += 1
        print(f"  ✓ {label}")
    else:
        print(f"  MISS: {label or repr(old[:50])}")

def s(path_d, w=16, h=16, col='currentColor'):
    """Return inline SVG string."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" fill="none" '
            f'viewBox="0 0 24 24" stroke="{col}" stroke-width="1.5">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="{path_d}"/></svg>')

CHIP   = 'M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18'
TOOL   = ('M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 '
          '2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 '
          '1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 '
          '1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426'
          '-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 '
          '2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z')
BOLT   = 'M13 10V3L4 14h7v7l9-11h-7z'
EYE    = 'M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z'
WARN   = 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'

print("── Critical object fixes ──")
fix("findings.push({sev:'info',icon:'??',label:'DISAPPEARED',",
    "findings.push({sev:'info',icon:_iconSvg('info','#64748b'),label:'DISAPPEARED',",
    "Finding: DISAPPEARED")

fix("layerHdr('??','TL;DR — Conclusive Direction','#a5b4fc')",
    "layerHdr(_iconSvg('eye','#a5b4fc'),'TL;DR — Conclusive Direction','#a5b4fc')",
    "layerHdr TL;DR")

fix("layerHdr('??','Key Signal — #1 Metric','#fbbf24')",
    "layerHdr(_iconSvg('lightning','#fbbf24'),'Key Signal — #1 Metric','#fbbf24')",
    "layerHdr Key Signal")

print("\n── Span/div icon replacements ──")
# Intelligence Engine round logo
fix('align-items:center;justify-content:center;font-size:16px;flex-shrink:0">??</div>',
    f'align-items:center;justify-content:center;font-size:16px;flex-shrink:0">{s(CHIP,18,18,"#ffffff")}</div>',
    "Intelligence circle logo")

# OraVision RCA header
fix('<span style="font-size:14px">??</span>',
    f'<span style="display:inline-flex;align-items:center">{s(EYE,14,14,"#a5b4fc")}</span>',
    "OraVision header icon")

# Disclaimer warning icon
fix('<span style="font-size:18px;flex-shrink:0;margin-top:1px;line-height:1">?</span>',
    f'<span style="display:inline-flex;align-items:flex-start;flex-shrink:0;margin-top:2px">{s(WARN,18,18,"#fbbf24")}</span>',
    "Disclaimer warning icon")

# Remaining font-size:16px spans with ??
n1, _ = 0, None
content, n1 = re.subn(
    r'<span style="font-size:16px">\?\?</span>',
    f'<span style="display:inline-flex;align-items:center">{s(TOOL,16,16,"currentColor")}</span>',
    content)
fixes += n1; print(f"  ✓ font-size:16px ?? spans: {n1}")

# Remaining font-size:16px spans with single ?
content, n2 = re.subn(
    r'<span style="font-size:16px">\?</span>',
    f'<span style="display:inline-flex;align-items:center">{s(BOLT,16,16,"currentColor")}</span>',
    content)
fixes += n2; print(f"  ✓ font-size:16px ? spans: {n2}")

print("\n── Badge/label text cleanups ──")
REPLACEMENTS = [
    # Snap type badges
    (">? JOB CAPTURE<",       ">JOB CAPTURE<",         "JOB CAPTURE badge"),
    (">?? SCHEDULED SNAP<",   ">SCHEDULED SNAP<",      "SCHEDULED SNAP badge"),
    (">? PARTIAL<",           ">PARTIAL<",             "PARTIAL badge"),
    # Trend badges
    (">? WORSENING<",         ">▲ WORSENING<",         "WORSENING badge"),
    (">? IMPROVING<",         ">▼ IMPROVING<",         "IMPROVING badge"),
    # Parallel markers
    (">? PARALLEL<",          ">⟥ PARALLEL<",          "PARALLEL badge"),
    ("? PARALLEL</span>",     "⟥ PARALLEL</span>",    "PARALLEL span close"),
    ("? PARALLEL SQL",        "PARALLEL SQL",          "PARALLEL SQL text"),
    ("'? PARALLEL'",          "'⟥ PARALLEL'",          "PARALLEL string literal"),
    # Status badges
    (">? HIGH<",              ">● HIGH<",              "HIGH badge"),
    (">?? SILENT offenders:", ">● SILENT offenders:",  "SILENT offenders"),
    # Section headers
    (">?? CORRELATED SIGNALS",">CORRELATED SIGNALS",   "CORRELATED SIGNALS"),
    (">? WHAT TO DO NOW<",    ">WHAT TO DO NOW<",      "WHAT TO DO NOW"),
    # Causal / arrow indicators
    ("? Causal chain:",       "↳ Causal chain:",       "Causal chain"),
    ("? causal chain:",       "↳ causal chain:",       "causal chain lower"),
    ("? causing ?",           "→",                     "causing arrow"),
    # Side-effect markers
    (">? SIDE-EFFECT",        ">↳ SIDE-EFFECT",        "SIDE-EFFECT"),
    (">? EXPLAINED<",         ">✓ EXPLAINED<",         "EXPLAINED"),
    (">? LINKED TO VERDICT<", ">✓ LINKED TO VERDICT<", "LINKED TO VERDICT"),
    # Button text
    ("'? diagnose'",          "'diagnose'",            "diagnose button str"),
    ("? diagnose</button>",   "diagnose</button>",     "diagnose button close"),
    (">? diagnose<",          ">diagnose<",            "diagnose button inner"),
    ("'>? diagnose'",         "'>diagnose'",           "diagnose btn cond"),
    (">? Fix<",               ">Fix<",                 "Fix label"),
    (">? Evidence<",          ">Evidence<",            "Evidence label"),
    (">? reasoning<",         ">reasoning<",           "reasoning btn"),
    ("'? reasoning'",         "'reasoning'",           "reasoning btn str"),
    (">?? exec<",             ">exec<",                "exec table header"),
    # Oracle ref markers
    ("?? ${esc(f.oracle_ref)}",            "${esc(f.oracle_ref)}",           "oracle_ref f"),
    ("?? ${esc(topFinding.oracle_ref)}",   "${esc(topFinding.oracle_ref)}",  "oracle_ref topFinding"),
    # Dismiss button
    (">? Dismiss<",           ">× Dismiss<",           "Dismiss btn"),
    ("? Dismiss<",            "× Dismiss<",            "Dismiss btn close"),
    # Advisory text markers
    (">? Hard Parses",        ">Hard Parses",          "Hard Parses alert"),
    (">? db file sequential", ">db file sequential",   "db file seq alert"),
    (">? log file sync",      ">log file sync",        "log file sync alert"),
    (">? Windows differ",     ">Note: Windows differ", "Windows differ"),
    (">? s/exec is",          ">Note: s/exec is",      "s/exec note"),
    (">? No significant issues",">No significant issues","No issues msg"),
    # Correlation markers in template expressions
    ("? ${corr.type.replace(",    "${corr.type.replace(",   "corr type badge"),
    ("? ${corrLink.signal",       "${corrLink.signal",       "corrLink signal"),
    ('"? ${esc(corrLink.signal',  '"${esc(corrLink.signal',  "corrLink esc"),
    (">?? ${esc(n)}</div>",       ">${esc(n)}</div>",        "corrNotes prefix"),
    # Tool-assisted badge
    ("> Tool-assisted analysis<", "> Tool-assisted analysis<", "Tool-assisted (noop)"),
]

for old, new, label in REPLACEMENTS:
    fix(old, new, label)

# Tool-assisted: strip any leading ? before the word
content, nt = re.subn(r'>\?\s*Tool-assisted', '>Tool-assisted', content)
fixes += nt; print(f"  ✓ Tool-assisted badge cleanup: {nt}")

# cross-link pane clear button
content, nc = re.subn(r'>\?\s*clear<', '>× clear<', content)
fixes += nc; print(f"  ✓ clear button: {nc}")

# ?? Related wait events / Correlated SQLs
content, nrw = re.subn(r'\?\?\s*(Related wait events)', r'\1', content)
fixes += nrw; print(f"  ✓ Related wait events: {nrw}")

content, ncs = re.subn(r'\?\?\s*(Correlated SQLs)', r'\1', content)
fixes += ncs; print(f"  ✓ Correlated SQLs: {ncs}")

# Action Priority header (next action const)
content, nap = re.subn(
    r'<span style="font-size:16px">\?</span>(?=\s*<span[^>]*>Action Priority)',
    f'<span style="display:inline-flex;align-items:center">{s(BOLT,16,16,"#34d399")}</span>',
    content)
fixes += nap; print(f"  ✓ Action Priority icon: {nap}")

# Final broad catch for ?? LABEL: patterns
content, nlab = re.subn(r'\?\? ([A-Z][A-Z& ]+:)', r'● \1', content)
fixes += nlab; print(f"  ✓ ?? LABEL: patterns: {nlab}")

# Clean up any residual '?? TEXT' in quoted strings (badge content)
content, nqs = re.subn(r"'\?\? ([^']{3,40})'", r"'● \1'", content)
fixes += nqs; print(f"  ✓ '?? ...' quoted strings: {nqs}")

print(f"\n{'='*50}")
print(f"  Total fixes: {fixes}")
print(f"  File size:   {len(content):,} chars  (delta {len(content)-original_len:+,})")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"\n✅  Written: {FILE}")
