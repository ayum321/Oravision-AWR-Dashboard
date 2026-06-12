# -*- coding: utf-8 -*-
"""
Improve SQL Analysis tab: Replace single monolithic table with tabbed sections.
3 tabs: Common SQLs | New SQLs | Disappeared
"""

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the old table section
old_start_marker = '<!-- 3. Complete SQL Table (COMMON section sortable) -->'
old_start = content.index(old_start_marker)

# Find the end - the closing of this section before the function closing
old_end_marker = "    `;\n\n}"
old_end_search = content.find(old_end_marker, old_start)
old_end = old_end_search + len("    `;")

old_section = content[old_start:old_end]
print(f"Found old SQL table section: {len(old_section)} chars at L{content[:old_start].count(chr(10))+1}")

# Build new tabbed section
new_section = r'''<!-- 3. SQL Comparison Tables — Tabbed Layout -->
        <div class="mt-4 mb-5">
            <!-- Tab header bar -->
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:8px">
                <div style="display:flex;gap:0;border-radius:8px;overflow:hidden;border:1px solid #1e293b">
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-common').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(16,185,129,0.15)';this.style.color='#34d399'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:rgba(16,185,129,0.15);color:#34d399;border:none;cursor:pointer;transition:all 0.2s">
                        Common (${common.length})
                    </button>
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-new').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(139,92,246,0.15)';this.style.color='#a78bfa'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:transparent;color:#64748b;border:none;border-left:1px solid #1e293b;cursor:pointer;transition:all 0.2s">
                        New in ${esc(lbl2)} (${newSqls.length})
                    </button>
                    <button onclick="(function(){document.querySelectorAll('.sql-tab-pane').forEach(p=>p.style.display='none');document.getElementById('sql-pane-gone').style.display='';document.querySelectorAll('.sql-tab-btn').forEach(b=>{b.style.background='transparent';b.style.color='#64748b'});this.style.background='rgba(6,182,212,0.1)';this.style.color='#67e8f9'}).call(this)" class="sql-tab-btn" style="padding:6px 16px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;background:transparent;color:#64748b;border:none;border-left:1px solid #1e293b;cursor:pointer;transition:all 0.2s">
                        Disappeared (${disappeared.length})
                    </button>
                </div>
                <div class="flex items-center gap-4">
                    <label class="flex items-center gap-1 text-[10px] text-gray-400 cursor-pointer">
                        <input type="checkbox" id="sys-sql-toggle" onchange="toggleSysSQL(this.checked)" style="accent-color:#6366f1">
                        Show System SQLs <span class="text-gray-600">(${_sysCount} hidden)</span>
                    </label>
                    <div class="text-[10px] text-gray-500">Click headers to sort</div>
                </div>
            </div>

            <!-- PANE 1: Common SQLs -->
            <div id="sql-pane-common" class="sql-tab-pane card overflow-x-auto" style="max-height:500px;overflow-y:auto">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        ${sth('Elapsed/Exec ('+esc(lbl1)+')','epe1','Sort by baseline elapsed per execution')}
                        ${sth('Elapsed/Exec ('+esc(lbl2)+')','epe2','Sort by problem elapsed per execution')}
                        ${sth('Elapsed \u0394%','epeD','Sort by % change in elapsed per execution')}
                        ${sth('Execs ('+esc(lbl1)+')','execs1','Sort by baseline execution count')}
                        ${sth('Execs ('+esc(lbl2)+')','execs2','Sort by problem execution count')}
                        ${sth('Execs \u0394%','execD','Sort by % change in executions')}
                        ${sth('%DB ('+esc(lbl1)+')','pctDb1','Sort by % DB time baseline')}
                        ${sth('%DB ('+esc(lbl2)+')','pctDb2','Sort by % DB time problem')}
                        ${sth('CPU% Shift','cpuShift','Sort by CPU ratio change')}
                    </tr></thead>
                    <tbody id="sql-common-tbody">${commonRows}</tbody>
                </table>
                ${common.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No common SQLs found between the two periods</div>' : ''}
            </div>

            <!-- PANE 2: New SQLs -->
            <div id="sql-pane-new" class="sql-tab-pane card overflow-x-auto" style="max-height:500px;overflow-y:auto;display:none">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        <th>Elapsed/Exec</th>
                        <th>Executions</th>
                        <th>%DB Time</th>
                        <th>CPU%</th>
                        <th colspan="4">Notes</th>
                    </tr></thead>
                    <tbody id="sql-new-tbody">${newRows}</tbody>
                </table>
                ${newSqls.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No new SQLs in the problem period</div>' : ''}
            </div>

            <!-- PANE 3: Disappeared -->
            <div id="sql-pane-gone" class="sql-tab-pane card overflow-x-auto" style="max-height:500px;overflow-y:auto;display:none">
                <table class="rca-table text-xs">
                    <thead><tr>
                        <th style="width:30px">#</th>
                        <th>SQL ID</th>
                        <th>Status</th>
                        <th>Elapsed/Exec</th>
                        <th>Executions</th>
                        <th>%DB Time</th>
                        <th>CPU%</th>
                        <th colspan="4">Notes</th>
                    </tr></thead>
                    <tbody id="sql-disappeared-tbody">${disappearedRows}</tbody>
                </table>
                ${disappeared.length === 0 ? '<div class="text-center text-gray-500 text-xs py-8">No disappeared SQLs between the two periods</div>' : ''}
            </div>
        </div>
    '''

content = content[:old_start] + new_section + content[old_end:]

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"SQL Analysis tab: monolithic table replaced with 3-tab layout")
print(f"Braces: {content.count('{')}/{content.count('}')}")
print(f"Divs: {content.count('<div')}/{content.count('</div>')}")
