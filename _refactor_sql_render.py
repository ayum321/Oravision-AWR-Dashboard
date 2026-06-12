"""
Add evidence/confidence rendering to the SQL comparison UI:
1. Add inconclusiveMsg + criticalCommon/criticalNew to destructuring
2. Add confidence badge to _buildCommonRow
3. Add inconclusive message banner to the summary section
"""
import sys

path = r"backend\templates\index.html"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

changes = 0

# ═════ FIX 1: Update destructuring to include new fields ═════
old_destr = "const { common, newSqls, disappeared,\n            planChangedCount, planImprovedCount, regressionCount, slowerCount, improvedCount, criticalNewCount } = rpt;"
if old_destr not in src:
    # Try with different whitespace
    old_destr = "const { common, newSqls, disappeared,"
    idx = src.find(old_destr)
    if idx >= 0:
        end_idx = src.find("} = rpt;", idx) + len("} = rpt;")
        old_block = src[idx:end_idx]
        new_block = "const { common, newSqls, disappeared, criticalCommon, criticalNew,\n            planChangedCount, planImprovedCount, regressionCount, slowerCount, improvedCount, criticalNewCount,\n            inconclusiveMsg, hasStrongEvidence } = rpt;"
        src = src[:idx] + new_block + src[end_idx:]
        changes += 1
        print(f"FIX {changes}: Updated destructuring with new fields")
    else:
        print("ERROR: Cannot find destructuring")
        sys.exit(1)
else:
    new_destr = "const { common, newSqls, disappeared, criticalCommon, criticalNew,\n            planChangedCount, planImprovedCount, regressionCount, slowerCount, improvedCount, criticalNewCount,\n            inconclusiveMsg, hasStrongEvidence } = rpt;"
    src = src.replace(old_destr, new_destr)
    changes += 1
    print(f"FIX {changes}: Updated destructuring with new fields")

# ═════ FIX 2: Add confidence badge to the common row status column ═════
# Add confidence indicator after the status tag in _buildCommonRow
old_status_tag = """        <td><span class="sql-tag ${t.cls}">${t.label}</span></td>

        <td class="text-Cgreen font-semibold text-sm">${num(c.good.elapsedPerExec,3)}s</td>"""

if old_status_tag in src:
    new_status_tag = """        <td><span class="sql-tag ${t.cls}">${t.label}</span>${c.confidence ? '<span style="font-size:8px;padding:1px 4px;border-radius:3px;margin-left:4px;font-weight:700;' + (c.confidence==='HIGH'?'background:#064e3b;color:#6ee7b7':c.confidence==='MEDIUM'?'background:#451a03;color:#fbbf24':'background:#1e293b;color:#64748b') + '">' + c.confidence + '</span>' : ''}</td>

        <td class="text-Cgreen font-semibold text-sm">${num(c.good.elapsedPerExec,3)}s</td>"""
    src = src.replace(old_status_tag, new_status_tag)
    changes += 1
    print(f"FIX {changes}: Added confidence badge to common row")
else:
    print("WARN: Could not find status tag for confidence badge")

# ═════ FIX 3: Add inconclusive message banner ═════
# Find the SQL summary section and add the inconclusive banner
# Look for the SQL summary kpi cards section
old_kpi_marker = '            <div class="kpi-card" style="border-top:3px solid ${planChangedCount>0'
idx = src.find(old_kpi_marker)
if idx >= 0:
    # Insert inconclusive banner before the KPI cards
    inconclusive_banner = """            <!-- Inconclusive verdict banner -->
            ${inconclusiveMsg ? '<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:8px;padding:12px 18px;margin-bottom:16px;display:flex;align-items:center;gap:10px"><span style="font-size:16px">\u26A0\uFE0F</span><span style="color:#fbbf24;font-size:12px;font-weight:600">' + inconclusiveMsg + '</span></div>' : ''}
"""
    src = src[:idx] + inconclusive_banner + src[idx:]
    changes += 1
    print(f"FIX {changes}: Added inconclusive verdict banner")
else:
    print("WARN: Could not find KPI card section for inconclusive banner")

# ═════ FIX 4: Add evidence score to the detail panel ═════
# Add evidence section to the detail panel in _buildCommonRow
old_ash_section = "(ashEvt || ashSrc\n            ? '<div style=\"border-top:1px solid #1e293b;padding-top:10px\">' +"
if old_ash_section in src:
    evidence_section = """// Evidence scoring display
        (c.evidenceScore !== undefined
            ? '<div style="border-top:1px solid #1e293b;padding-top:10px;margin-top:6px">' +
              '<div style="color:#818cf8;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px">Evidence Summary</div>' +
              '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
              '<span style="background:#1e1b4b;color:#a5b4fc;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:700">Score: ' + c.evidenceScore + '/100</span>' +
              '<span style="font-size:10px;padding:2px 8px;border-radius:4px;font-weight:700;' + (c.confidence==='HIGH'?'background:#064e3b;color:#6ee7b7':c.confidence==='MEDIUM'?'background:#451a03;color:#fbbf24':'background:#1e293b;color:#64748b') + '">' + c.confidence + ' confidence</span>' +
              (c.supportingSections > 0 ? '<span style="background:#0c2340;color:#7dd3fc;font-size:10px;padding:2px 8px;border-radius:4px">Confirmed in ' + c.supportingSections + ' other AWR section' + (c.supportingSections > 1 ? 's' : '') + '</span>' : '') +
              (c.ashSupports ? '<span style="background:#1e3a5f;color:#93c5fd;font-size:10px;padding:2px 8px;border-radius:4px">ASH corroborates</span>' : '') +
              '</div>' +
              '</div>'
            : '') +

        """ + old_ash_section
    src = src.replace(old_ash_section, evidence_section)
    changes += 1
    print(f"FIX {changes}: Added evidence summary to detail panel")
else:
    print("WARN: Could not find ASH section marker for evidence display")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print(f"\n=== All {changes} rendering fixes applied ===")
