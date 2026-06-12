function renderSessionIntelligencePanel(ctx) {
    // Pull session_intelligence from report data
    const report = ctx._raw?.report || ctx._raw?.data?.report || {};
    let si = report.session_intelligence;

    // Fallback: synthesize from loadProfile if backend didn't provide it
    if (!si) {
        const lp = ctx.loadProfile || {};
        const lpG = lp.good || {}, lpB = lp.bad || {};
        const elG = (ctx.meta?.good?.elapsed_min || 1) * 60;
        const elB = (ctx.meta?.bad?.elapsed_min || 1) * 60;
        const _aasG = ctx.aas?.good || 0, _aasB = ctx.aas?.bad || 0;
        const cpuCnt = ctx.meta?.cpu_count || 1;
        const logonsG = lpG.logons || 0, logonsB = lpB.logons || 0;
        const connMgmtG = ctx.timeModel?.good?.connection_mgmt || 0;
        const connMgmtB = ctx.timeModel?.bad?.connection_mgmt || 0;
        const execsG = lpG.executes || 0, execsB = lpB.executes || 0;
        const parsesG = lpG.parses || 0, parsesB = lpB.parses || 0;
        const hpG = lpG.hard_parses || 0, hpB = lpB.hard_parses || 0;
        const ucG = lpG.user_calls || 0, ucB = lpB.user_calls || 0;
        const txnG = lpG.transactions || 0, txnB = lpB.transactions || 0;

        // Compute logon deltas
        const _logDelta = logonsG > 0.01 ? ((logonsB - logonsG) / logonsG * 100) : (logonsB > 0 ? 100 : 0);
        const _logAbs = logonsB - logonsG;
        const _execDelta = execsG > 0 ? ((execsB - execsG) / execsG * 100) : (execsB > 0 ? 100 : 0);

        // Derive stability pattern from Oracle-expert session behavior analysis
        const _cumG = logonsG * elG, _cumB = logonsB * elB;
        const _cumRatio = _cumG > 0 ? _cumB / _cumG : 1;
        const _execPerLogG = _cumG > 100 ? (execsG * elG / _cumG) : 0;
        const _execPerLogB = _cumB > 100 ? (execsB * elB / _cumB) : 0;
        const _eplDrop = _execPerLogG > 50 ? ((_execPerLogB - _execPerLogG) / _execPerLogG * 100) : 0;
        const _hpSpike = hpG > 0 ? ((hpB - hpG) / hpG * 100) : (hpB > 1 ? 100 : 0);
        const _connCostG = _cumG > 0 ? (connMgmtG / _cumG * 1000) : 0;
        const _connCostB = _cumB > 0 ? (connMgmtB / _cumB * 1000) : 0;
        const _aasRatio = cpuCnt > 0 ? _aasB / cpuCnt : 0;

        // Pattern classification (Oracle PE expert logic)
        let _pattern, _patternDetail;
        if (_logDelta > 100 && _hpSpike > 40 && connMgmtB > connMgmtG * 1.5) {
            _pattern = 'LOGON_STORM';
            _patternDetail = 'All 3 storm indicators: logon rate +' + Math.round(_logDelta) + '%, hard parses +' + Math.round(_hpSpike) + '%, conn mgmt elevated.';
        } else if (_eplDrop < -25 && _logDelta > 50) {
            _pattern = 'HIGH_CHURN';
            _patternDetail = 'Sessions doing less work each (exec/logon dropped ' + Math.abs(Math.round(_eplDrop)) + '%) despite +' + Math.round(_logDelta) + '% logons — pool thrashing or retry loop.';
        } else if (_aasRatio > 2 && _logDelta > 20) {
            _pattern = 'AAS_DRIVEN_CHURN';
            _patternDetail = 'AAS ' + _aasB.toFixed(1) + ' is ' + _aasRatio.toFixed(1) + '× CPUs. Session growth is secondary to wait/CPU saturation.';
        } else if (_logDelta < -20) {
            _pattern = 'NORMAL_CYCLING';
            _patternDetail = 'Logon rate decreased ' + Math.round(_logDelta) + '% — no connection pressure. Focus on SQL and wait events.';
        } else if (Math.abs(_logDelta) <= 30 && Math.abs(_execDelta) <= 30) {
            _pattern = 'NORMAL_CYCLING';
            _patternDetail = 'Stable 