import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1a: Add Duration field after s1 Time field + window diff banner
old_s1 = '''                    <div class="db-info-field"><span class="field-label">Time:</span><span class="field-value">${esc(s1.begin_time||'')} to ${esc(s1.end_time||'')}</span></div>

                </div>

            </div>

            <div class="p-3 rounded-lg" style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2)">'''

new_s1 = '''                    <div class="db-info-field"><span class="field-label">Time:</span><span class="field-value">${esc(s1.begin_time||'')} to ${esc(s1.end_time||'')}</span></div>

                    <div class="db-info-field"><span class="field-label">Duration:</span><span class="field-value">${s1.elapsed_min ? num(s1.elapsed_min,1)+' min' : 'N/A'}</span></div>

                </div>

            </div>

            ${(() => {
                const gMin = s1.elapsed_min || 0, bMin = s2.elapsed_min || 0;
                if (gMin > 0 && bMin > 0) {
                    const pct = ((bMin - gMin) / gMin * 100);
                    if (Math.abs(pct) > 10) {
                        return '<div class="col-span-2 text-center py-1.5 px-3 rounded text-xs" style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.25);color:#fbbf24">'
                            + '\\u26a0 Windows differ ' + (pct > 0 ? '+' : '') + pct.toFixed(0) + '% (good: ' + gMin.toFixed(1) + ' min, bad: ' + bMin.toFixed(1) + ' min) \\u2014 execution counts normalized to per-minute rates'
                            + '</div>';
                    }
                }
                return '';
            })()}

            <div class="p-3 rounded-lg" style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2)">'''

assert old_s1 in content, "Could not find s1 Time block"
content = content.replace(old_s1, new_s1, 1)

# Fix 1b: Add Duration field after s2 Time field
old_s2 = '''                    <div class="db-info-field"><span class="field-label">Time:</span><span class="field-value">${esc(s2.begin_time||'')} to ${esc(s2.end_time||'')}</span></div>

                </div>

            </div>

        </div>

    </div>`;

}'''

new_s2 = '''                    <div class="db-info-field"><span class="field-label">Time:</span><span class="field-value">${esc(s2.begin_time||'')} to ${esc(s2.end_time||'')}</span></div>

                    <div class="db-info-field"><span class="field-label">Duration:</span><span class="field-value">${s2.elapsed_min ? num(s2.elapsed_min,1)+' min' : 'N/A'}</span></div>

                </div>

            </div>

        </div>

    </div>`;

}'''

assert old_s2 in content, "Could not find s2 Time block"
content = content.replace(old_s2, new_s2, 1)

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix 1 applied: Duration fields + window diff banner")
