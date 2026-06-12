with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 2a: Enhance classifyBottleneck to track top event within dominant class
old_func = '''function classifyBottleneck(waitEvents) {
    if (!waitEvents || !waitEvents.length) return { type: 'unknown', label: 'Unknown', pct: 0 };
    const byClass = {};
    for (const we of waitEvents) {
        const cls = (we.wait_class || '').toLowerCase();
        if (!cls || cls === 'idle') continue;
        // Map to canonical bottleneck types
        let mapped = cls;
        if (/user io|system io/i.test(cls)) mapped = 'io';
        else if (/concurren/i.test(cls)) mapped = 'concurrency';
        else if (/commit/i.test(cls)) mapped = 'commit';
        else if (/configur/i.test(cls)) mapped = 'configuration';
        else if (/network/i.test(cls)) mapped = 'network';
        else if (/cpu/i.test(we.event_name || '')) mapped = 'cpu';
        byClass[mapped] = (byClass[mapped] || 0) + (we.pct_db_time || 0);
    }
    // Also consider DB CPU separately
    const cpuEv = waitEvents.find(e => /DB CPU/i.test(e.event_name));
    if (cpuEv) byClass['cpu'] = (byClass['cpu'] || 0) + (cpuEv.pct_db_time || 0);

    const sorted = Object.entries(byClass).sort((a,b) => b[1] - a[1]);
    if (!sorted.length) return { type: 'unknown', label: 'Unknown', pct: 0 };

    // Single dominant bottleneck (>60%)
    if (sorted[0][1] > 60) {
        return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1] };
    }
    // Mixed (top two both >15%)
    const above15 = sorted.filter(([_, pct]) => pct > 15);
    if (above15.length >= 2) {
        return {
            type: 'mixed',
            label: above15.slice(0, 2).map(([c]) => _bottleneckLabel(c)).join(' + '),
            pct: above15.reduce((s, [_, p]) => s + p, 0),
            classes: above15
        };
    }
    return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1] };
}'''

new_func = '''function classifyBottleneck(waitEvents) {
    if (!waitEvents || !waitEvents.length) return { type: 'unknown', label: 'Unknown', pct: 0, descriptor: '' };
    const byClass = {};
    const eventsByClass = {};
    for (const we of waitEvents) {
        const cls = (we.wait_class || '').toLowerCase();
        if (!cls || cls === 'idle') continue;
        let mapped = cls;
        if (/user io|system io/i.test(cls)) mapped = 'io';
        else if (/concurren/i.test(cls)) mapped = 'concurrency';
        else if (/commit/i.test(cls)) mapped = 'commit';
        else if (/configur/i.test(cls)) mapped = 'configuration';
        else if (/network/i.test(cls)) mapped = 'network';
        else if (/cpu/i.test(we.event_name || '')) mapped = 'cpu';
        byClass[mapped] = (byClass[mapped] || 0) + (we.pct_db_time || 0);
        if (!eventsByClass[mapped]) eventsByClass[mapped] = [];
        if (!/DB CPU/i.test(we.event_name || '')) {
            eventsByClass[mapped].push(we);
        }
    }
    const cpuEv = waitEvents.find(e => /DB CPU/i.test(e.event_name));
    if (cpuEv) byClass['cpu'] = (byClass['cpu'] || 0) + (cpuEv.pct_db_time || 0);

    const sorted = Object.entries(byClass).sort((a,b) => b[1] - a[1]);
    if (!sorted.length) return { type: 'unknown', label: 'Unknown', pct: 0, descriptor: '' };

    // Find top event within a given class
    function topEventDescriptor(classKey) {
        const events = (eventsByClass[classKey] || [])
            .sort((a, b) => (b.pct_db_time || 0) - (a.pct_db_time || 0));
        if (events.length && events[0].pct_db_time > 0) {
            const e = events[0];
            const avgMs = e.avg_wait_ms != null ? e.avg_wait_ms : (e.time_waited_ms && e.total_waits ? e.time_waited_ms / e.total_waits : 0);
            return e.event_name + ': ' + (e.pct_db_time || 0).toFixed(1) + '% DB time' + (avgMs > 0 ? ' \\u00b7 ' + avgMs.toFixed(2) + 'ms avg' : '');
        }
        if (classKey === 'cpu' && cpuEv) return 'DB CPU: ' + (cpuEv.pct_db_time || 0).toFixed(1) + '% DB time';
        return '';
    }

    // Single dominant bottleneck (>60%)
    if (sorted[0][1] > 60) {
        return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1], descriptor: topEventDescriptor(sorted[0][0]) };
    }
    // Mixed (top two both >15%)
    const above15 = sorted.filter(([_, pct]) => pct > 15);
    if (above15.length >= 2) {
        return {
            type: 'mixed',
            label: above15.slice(0, 2).map(([c]) => _bottleneckLabel(c)).join(' + '),
            pct: above15.reduce((s, [_, p]) => s + p, 0),
            classes: above15,
            descriptor: topEventDescriptor(above15[0][0]),
        };
    }
    return { type: sorted[0][0], label: _bottleneckLabel(sorted[0][0]), pct: sorted[0][1], descriptor: topEventDescriptor(sorted[0][0]) };
}'''

assert old_func in content, "Could not find classifyBottleneck function"
content = content.replace(old_func, new_func, 1)

# Fix 2b: Update ctx.bottleneck wiring to include descriptor
old_wire = '''    ctx.bottleneck.shifted = ctx.bottleneck.good.type !== ctx.bottleneck.bad.type;
    ctx.bottleneck.goodLabel = _bottleneckLabel(ctx.bottleneck.good.type);
    ctx.bottleneck.badLabel  = _bottleneckLabel(ctx.bottleneck.bad.type);'''

new_wire = '''    ctx.bottleneck.shifted = ctx.bottleneck.good.type !== ctx.bottleneck.bad.type;
    ctx.bottleneck.goodLabel = _bottleneckLabel(ctx.bottleneck.good.type);
    ctx.bottleneck.badLabel  = _bottleneckLabel(ctx.bottleneck.bad.type);
    ctx.bottleneck.goodDescriptor = ctx.bottleneck.good.descriptor || '';
    ctx.bottleneck.badDescriptor  = ctx.bottleneck.bad.descriptor || '';'''

assert old_wire in content, "Could not find bottleneck wiring"
content = content.replace(old_wire, new_wire, 1)

# Fix 2c: Update hero banner to show descriptor under bottleneck label
# Good period bottleneck display
old_good_bn = '''                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.goodLabel}</span></div>'''
new_good_bn = '''                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.goodLabel}</span>${ctx.bottleneck.goodDescriptor ? '<div class="text-[10px] text-gray-500 mt-0.5">' + ctx.bottleneck.goodDescriptor + '</div>' : ''}</div>'''

assert old_good_bn in content, "Could not find good bottleneck display"
content = content.replace(old_good_bn, new_good_bn, 1)

# Bad period bottleneck display
old_bad_bn = '''                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.badLabel}</span></div>'''
new_bad_bn = '''                    <div class="text-xs text-gray-400 mb-2">Bottleneck: <span class="text-cyan-400">${ctx.bottleneck.badLabel}</span>${ctx.bottleneck.badDescriptor ? '<div class="text-[10px] text-gray-500 mt-0.5">' + ctx.bottleneck.badDescriptor + '</div>' : ''}</div>'''

assert old_bad_bn in content, "Could not find bad bottleneck display"
content = content.replace(old_bad_bn, new_bad_bn, 1)

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix 2 applied: Bottleneck descriptor with top event name")
