#!/usr/bin/env python3
"""
Apply all remaining fixes:
1. Change 2-col to 3-col grid
2. Add Transactions/sec card between Panel 1 and Panel 2
3. Add tooltips to major sections
4. Add tooltip to Session & Logon panel
5. Add tooltip to Load Profile section
"""

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

count = 0

# FIX: Change 2-col to 3-col grid for metric panels
old1 = 'Two metric panels'
new1 = 'Three metric panels'
if old1 in content:
    content = content.replace(old1, new1, 1)
    count += 1
    print('1. Grid title updated')

old2 = '<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">\n\n\n\n'
new2 = '<div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">\n\n\n\n'
if old2 in content:
    content = content.replace(old2, new2, 1)
    count += 1
    print('2. Grid cols updated')

# FIX: Add Transactions/sec card between Panel 1 and Panel 2
marker = '<!-- PANEL 2: Session & Logon Pressure -->'
txn_card = """<!-- PANEL 1b: Transactions/sec — Business Throughput -->
                    <div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:16px" title="Transactions per second from AWR Load Profile (Per Second column). This is the most important business throughput signal.&#10;&#10;When DB Time rises but Transactions/sec falls, the database is spending MORE time producing LESS business output — a congestion pattern indicating queries are blocked or degraded.">
                        <div class="flex items-center justify-between mb-3">
                            <div>
                                <div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">📊 Transactions/sec</div>
                                <div class="text-[9px] text-gray-600 font-mono">AWR Load Profile · Per Second</div>
                            </div>
                            ${isCongestion
                                ? '<div style="background:rgba(239,68,68,0.2);border:1px solid rgba(239,68,68,0.5);border-radius:6px;padding:3px 10px"><span style="color:#ef4444;font-size:9px;font-weight:900;letter-spacing:0.5px">CONGESTION</span></div>'
                                : Math.abs(txnDelta)>15
                                    ? '<div style="background:rgba(245,158,11,0.2);border:1px solid rgba(245,158,11,0.5);border-radius:6px;padding:3px 10px"><span style="color:#f59e0b;font-size:9px;font-weight:900;letter-spacing:0.5px">CHANGED</span></div>'
                                    : '<div style="background:rgba(16,185,129,0.2);border:1px solid rgba(16,185,129,0.5);border-radius:6px;padding:3px 10px"><span style="color:#10b981;font-size:9px;font-weight:900;letter-spacing:0.5px">STABLE</span></div>'
                            }
                        </div>
                        <div class="flex items-end gap-4 mb-3">
                            <div>
                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl1)}</div>
                                <div class="text-xl font-black text-green-400">${num(txn1,1)}</div>
                            </div>
                            <div class="text-gray-600 text-lg mb-1">→</div>
                            <div>
                                <div class="text-[9px] text-gray-500 uppercase font-bold mb-0.5">${esc(lbl2)}</div>
                                <div class="text-xl font-black" style="color:${txnDelta<-15?'#ef4444':txnDelta<-5?'#f59e0b':'#10b981'}">${num(txn2,1)}</div>
                            </div>
                            <div style="margin-left:auto;text-align:right">
                                <div class="text-[9px] text-gray-500 uppercase">Delta</div>
                                <div class="text-xl font-black" style="color:${txnDelta<-15?'#ef4444':txnDelta<-5?'#f59e0b':txnDelta>15?'#10b981':'#94a3b8'}">${txnDelta>0?'+':''}${num(txnDelta,0)}%</div>
                            </div>
                        </div>
                        ${isCongestion
                            ? '<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);border-radius:5px;padding:8px 12px"><div style="color:#f87171;font-size:11px;font-weight:800;margin-bottom:3px">⚠ CONGESTION — more DB time, less business output</div><div style="color:#94a3b8;font-size:10px;line-height:1.5">DB Time rose +'+num(dbTimePctChg,0)+'% while Transactions/sec fell '+num(txnDelta,0)+'%. The database is doing more work but delivering fewer completed transactions — queries are blocked or degraded.</div></div>'
                            : '<div style="background:rgba(15,23,42,0.6);border-radius:6px;padding:8px"><div class="text-[9px] text-gray-500 uppercase font-bold mb-1">DB Time Δ</div><div class="font-bold text-sm" style="color:'+(dbTimePctChg>20?'#ef4444':dbTimePctChg>0?'#f59e0b':'#10b981')+'">'+(dbTimePctChg>0?'+':'')+num(dbTimePctChg,0)+'%</div><div class="text-[9px] text-gray-600">'+(Math.abs(txnDelta)<10?'Throughput steady':'Throughput shifted')+'</div></div>'
                        }
                    </div>

                    """

if marker in content:
    content = content.replace(marker, txn_card + marker, 1)
    count += 1
    print('3. Transactions/sec card added')

# FIX: Add tooltip to Session & Logon Pressure panel
old_session = '<!-- PANEL 2: Session & Logon Pressure -->\n                    <div style="background:${logonBg};border:1px solid ${logonCol}30;border-radius:10px;padding:16px">'
new_session = '<!-- PANEL 2: Session & Logon Pressure -->\n                    <div style="background:${logonBg};border:1px solid ${logonCol}30;border-radius:10px;padding:16px" title="Logon Pressure Score (LPS) = 0.5 × Δ(Logons/sec%) + 0.5 × Δ(Connection Management Time%).&#10;&#10;Measures how aggressively the application is creating new database sessions. High LPS indicates connection pool misconfiguration causing cold-cursor parse storms.&#10;&#10;Thresholds: LPS 0-20 STABLE, 20-50 MODERATE, 50-100 HIGH PRESSURE, >100 LOGON STORM">'
if old_session in content:
    content = content.replace(old_session, new_session, 1)
    count += 1
    print('4. Session panel tooltip added')

# FIX: Add tooltip to Load Profile Cross-Correlation section
old_lp_title = "Load Profile Cross-Correlation</div>"
# Find the one in the section header (not in other places)
lp_idx = content.find("Load Profile Cross-Correlation</div>")
if lp_idx > 0:
    # Check it's the right one (in the rendering section)
    before = content[max(0,lp_idx-100):lp_idx]
    if 'text-cyan-400' in before:
        old_lp = 'Load Profile Cross-Correlation</div>\n                        <div class="text-[9px] text-gray-600 ml-1">'
        new_lp = 'Load Profile Cross-Correlation</div>\n                        <div class="text-[9px] text-gray-600 ml-1" title="All values from the AWR Load Profile Per Second column. Only metrics with >10% delta shown. Negative deltas indicate the metric decreased in the problem period.">'
        if old_lp in content:
            content = content.replace(old_lp, new_lp, 1)
            count += 1
            print('5. Load Profile tooltip added')

# FIX: Add tooltip to Session Performance Intelligence header
old_spi = 'Session Performance Intelligence</div>\n                    <div class="text-[10px] text-gray-500">'
new_spi = 'Session Performance Intelligence</div>\n                    <div class="text-[10px] text-gray-500" title="Cross-correlates DB Response Latency, Session/Logon Pressure, Load Profile metrics, SQL Attribution, and Wait Events into a single diagnostic chain. Each node is evidence-linked — not generic.">'
if old_spi in content:
    content = content.replace(old_spi, new_spi, 1)
    count += 1
    print('6. SPI header tooltip added')

# FIX: Add tooltip to SQL 3-Zone section
old_sql3 = 'SQL Elapsed/Exec'
idx3 = content.find(old_sql3)
if idx3 > 0:
    before3 = content[max(0,idx3-200):idx3]
    if 'dash-sql' in before3 or 'card p-4 mb-4' in before3:
        old_sql3_full = '3-Zone Comparative Analysis</div>'
        new_sql3_full = '3-Zone Comparative Analysis</div>\n                <div class="text-[9px] text-gray-500" title="Divides SQL into three zones: Good-Only (disappeared in problem period), Common (found in both), Bad-Only (new in problem). Sorted by elapsed/exec. Helps identify whether regression comes from existing SQL getting slower or new SQL appearing.">'
        # Only replace the first occurrence
        if old_sql3_full in content:
            content = content.replace(old_sql3_full, new_sql3_full, 1)
            count += 1
            print('7. SQL 3-Zone tooltip added')

# FIX: Add tooltip to Connecting Dots Analysis header 
old_chain = 'Connecting Dots Analysis</div>'
if old_chain in content:
    new_chain = 'Connecting Dots Analysis</div>\n                <div class="text-[9px] text-gray-500 mb-1" title="Cross-references all evidence layers — Latency, Session Pressure, Load Profile, SQL Attribution, and Wait Events — to build a causal chain. Each node cites specific data; nothing is guessed. The chain identifies whether the root cause is SQL regression, connection churn, workload explosion, or a combination.">'
    content = content.replace(old_chain, new_chain, 1)
    count += 1
    print('8. Connecting Dots tooltip added')

# FIX: Add tooltip to Key Changes section
old_kc = 'Key Changes'
idx_kc = content.find("Key Changes")
if idx_kc > 0:
    # Only the categorized findings header
    before_kc = content[max(0,idx_kc-100):idx_kc]
    if 'Categorized' in before_kc or 'categorized' in content[idx_kc:idx_kc+100]:
        pass  # Already in the categorized findings section


with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nTotal replacements: {count}')
