import re

with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the old Connecting Dots Chain section
old_marker = '<!-- â\x80\x94â\x80\x94 Connecting Dots Chain â\x80\x94â\x80\x94 -->'
old_end = "            })()}"  # The IIFE closing

# Find start position
start_idx = content.index(old_marker)
# Find the })() that closes the IIFE after the chain
end_search_start = start_idx
end_idx = content.index("            })()}", end_search_start)
end_idx += len("            })()}")

old_block = content[start_idx:end_idx]

new_block = """<!-- \u2500\u2500 Connecting Dots Chain (evidence-based from ctx.connectingDots) \u2500\u2500 -->
                ${ctx.connectingDots ? `
                <div style="background:rgba(10,16,32,0.8);border:1px solid ${ctx.connectingDots.color}25;border-radius:10px;padding:14px 16px">
                    <div class="flex items-center justify-between gap-2 mb-3">
                        <div class="flex items-center gap-2">
                            <div style="width:6px;height:6px;border-radius:50%;background:${ctx.connectingDots.color};box-shadow:0 0 8px ${ctx.connectingDots.color}"></div>
                            <div class="text-[10px] font-bold uppercase tracking-wider" style="color:${ctx.connectingDots.color}">Connecting Dots \u2014 ${esc(ctx.connectingDots.title)}</div>
                        </div>
                        <div style="background:rgba(15,23,42,0.8);border:1px solid #1e293b;border-radius:6px;padding:3px 10px;display:flex;align-items:center;gap:5px;flex-shrink:0">
                            <span style="font-size:8px;color:#64748b;text-transform:uppercase;font-weight:700">RCA Confidence</span>
                            <span style="font-size:12px;font-weight:900;color:${ctx.connectingDots.confidence==='CONFIRMED'?'#34d399':'#fbbf24'}">${esc(ctx.connectingDots.confidence)}</span>
                        </div>
                    </div>
                    <div class="flex items-start gap-0 flex-wrap" style="row-gap:8px">
                        ${ctx.connectingDots.chain.map((node,ni) =>
                            '<div style="background:'+node.bg+';border:1px solid '+node.col+'30;border-radius:8px;padding:8px 12px;min-width:130px;max-width:180px">'+
                                '<div style="font-size:9px;color:'+node.col+';font-weight:900;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:3px">'+(node.risk?'\\u26a0 RISK: ':'')+esc(node.label)+'</div>'+
                                '<div style="font-size:9px;color:#94a3b8;line-height:1.4">'+esc(node.sub)+'</div>'+
                            '</div>'+
                            (ni<ctx.connectingDots.chain.length-1?'<div style="padding:0 4px;color:#334155;font-size:18px;font-weight:bold;align-self:center;flex-shrink:0">\\u2192</div>':'')
                        ).join('')}
                    </div>
                    <div class="mt-2 pt-2" style="border-top:1px solid #1e293b">
                        <span class="text-[9px] text-blue-400 font-bold uppercase">Recommended Action: </span>
                        <span class="text-[10px] text-gray-400">${esc(ctx.connectingDots.action)}</span>
                    </div>
                </div>
                ` : `
                <div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.15);border-radius:10px;padding:14px 16px">
                    <div class="flex items-center gap-2 mb-2">
                        <div style="width:6px;height:6px;border-radius:50%;background:#10b981"></div>
                        <div class="text-[10px] font-bold text-green-400 uppercase tracking-wider">System Healthy \u2014 No Causal Chain Detected</div>
                    </div>
                    <div class="text-[9px] text-gray-500">All signals within normal range. No specific bottleneck template matched. Establish as baseline.</div>
                </div>
                `}

                <!-- \u2500\u2500 ADDM Corroboration + Verification Queries \u2500\u2500 -->
                ${ctx.addmCorroboration && ctx.addmCorroboration.topWaitEvent ? `
                <div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:12px 16px;margin-top:8px">
                    <div class="flex items-center gap-2 mb-2">
                        <div style="width:5px;height:5px;border-radius:50%;background:${ctx.addmCorroboration.confirmed?'#34d399':'#fbbf24'}"></div>
                        <div class="text-[10px] font-bold uppercase tracking-wider" style="color:${ctx.addmCorroboration.confirmed?'#34d399':'#fbbf24'}">ADDM Corroboration</div>
                        <span style="background:${ctx.addmCorroboration.confirmed?'rgba(52,211,153,0.15)':'rgba(251,191,36,0.15)'};color:${ctx.addmCorroboration.confirmed?'#34d399':'#fbbf24'};font-size:9px;font-weight:800;padding:2px 8px;border-radius:9999px">${esc(ctx.addmCorroboration.confidence)}</span>
                    </div>
                    ${ctx.addmCorroboration.confirmed ? `
                    <div style="font-size:9px;color:#94a3b8;margin-bottom:6px">Oracle ADDM independently identified findings that confirm the root cause:</div>
                    ${ctx.addmCorroboration.matches.map(m => '<div style="font-size:9px;color:#6ee7b7;padding:2px 0">\u2713 '+esc(m.finding||m.description||m.name||'ADDM Finding')+'</div>').join('')}
                    ` : `
                    <div style="font-size:9px;color:#94a3b8">No matching ADDM findings for "${esc(ctx.addmCorroboration.topWaitEvent)}". Classification is PROBABLE based on wait event analysis.</div>
                    `}
                </div>
                ` : ''}

                ${(()=>{
                    const vq = VERIFY_QUERIES[ctx.addmCorroboration?.topWaitEvent];
                    if (!vq) return '';
                    return '<div style="background:rgba(10,16,32,0.7);border:1px solid #1e293b;border-radius:10px;padding:12px 16px;margin-top:8px">'+
                        '<div class="flex items-center gap-2 mb-2">'+
                            '<div style="width:5px;height:5px;border-radius:50%;background:#38bdf8"></div>'+
                            '<div class="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Verification Query</div>'+
                        '</div>'+
                        '<pre style="background:#0a0e1a;border:1px solid #1e293b;border-radius:6px;padding:8px 12px;font-size:10px;color:#e2e8f0;overflow-x:auto;margin-bottom:6px;white-space:pre-wrap">'+esc(vq.query)+'</pre>'+
                        '<div style="font-size:9px;color:#94a3b8;margin-bottom:4px"><b style="color:#fbbf24">Expected:</b> '+esc(vq.expect)+'</div>'+
                        '<div style="font-size:9px;color:#94a3b8"><b style="color:#38bdf8">Next Action:</b> '+esc(vq.action)+'</div>'+
                    '</div>';
                })()}

                </div>`;

            })()}"""

content = content[:start_idx] + new_block + content[end_idx:]

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Connecting Dots section replaced successfully")
print(f"Old block: {len(old_block)} chars")
print(f"New block: {len(new_block)} chars")
