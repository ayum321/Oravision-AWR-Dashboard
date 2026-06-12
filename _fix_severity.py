with open('backend/templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 3: Enhance severity to detect when baseline was stressed
# Insert goodAASRatio computation after bufHitDelta, then update the severity chain

old_severity = '''    let severity;
    if (dtChange > 0 && txDelta < -15 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 50 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 0 && topWaitDelta > 5) {
        severity = 'DEGRADED';
    } else if (dtChange < -10 && (physDelta > 100 || bufHitDelta < -5)) {
        severity = 'WORKLOAD_SHIFT';
    } else if (dtChange < -10 && e2pDelta >= -5 && bufHitDelta >= -5) {
        severity = 'IMPROVED';
    } else if (Math.abs(dtChange) < 10 && topWaitDelta < 3) {
        severity = 'STABLE';
    } else if (dtChange > 0) {
        severity = 'DEGRADED';
    } else {
        severity = 'STABLE';
    }
    // Override: never STABLE/IMPROVED when key indicators are bad
    if ((severity === 'STABLE' || severity === 'IMPROVED') &&
        (txDelta < -15 || e2pDelta < -5 || bufHitDelta < -5 || physDelta > 100)) {
        severity = 'WORKLOAD_SHIFT';
    }'''

new_severity = '''    const goodAASRatio = cpus > 0 ? (aasG / cpus) : 0;

    let severity;
    if (dtChange > 0 && txDelta < -15 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 50 && topWaitDelta > 10) {
        severity = 'CRITICAL';
    } else if (dtChange > 0 && topWaitDelta > 5) {
        severity = 'DEGRADED';
    } else if (dtChange < -10 && goodAASRatio > 0.80) {
        // Baseline was near-saturated: improvement is just lighter workload, not a fix
        severity = 'WORKLOAD_SHIFT';
    } else if (dtChange < -10 && (physDelta > 100 || bufHitDelta < -5)) {
        severity = 'WORKLOAD_SHIFT';
    } else if (dtChange < -10 && goodAASRatio < 0.70 && txDelta > -10 && e2pDelta >= -5 && bufHitDelta >= -5) {
        // Genuine improvement: DB time fell, baseline was not stressed, transactions held
        severity = 'IMPROVED';
    } else if (dtChange < -10 && e2pDelta >= -5 && bufHitDelta >= -5) {
        severity = 'IMPROVED';
    } else if (Math.abs(dtChange) < 10 && topWaitDelta < 3) {
        severity = 'STABLE';
    } else if (dtChange > 0) {
        severity = 'DEGRADED';
    } else {
        severity = 'STABLE';
    }
    // Override: never STABLE/IMPROVED when key indicators are bad
    if ((severity === 'STABLE' || severity === 'IMPROVED') &&
        (txDelta < -15 || e2pDelta < -5 || bufHitDelta < -5 || physDelta > 100)) {
        severity = 'WORKLOAD_SHIFT';
    }'''

assert old_severity in content, "Could not find severity chain"
content = content.replace(old_severity, new_severity, 1)

with open('backend/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix 3 applied: IMPROVED verdict with stressed baseline detection")
