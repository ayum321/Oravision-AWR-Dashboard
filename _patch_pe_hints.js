        // PE Field Knowledge — deeper optimization hints
        if (s.gpe > 100000 && s.executions > 10) {
            hints.push({icon:'\u{1F50D}', text:'INDEX CHECK: ' + comma(Math.round(s.gpe)) + ' gets/exec with ' + comma(s.executions) + ' execs. If Full Table Scan in plan, verify indexes on WHERE clause columns. Run: SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(\'' + esc(s.sql_id) + '\'));'});
        }
        if (s.gpe > 50000 && s.rows_processed > 0 && (s.gpe / Math.max(s.rows_processed,1)) > 500) {
            hints.push({icon:'\u{1F4D0}', text:'CARDINALITY SUSPECT: Gets/Row ratio = ' + comma(Math.round(s.gpe / Math.max(s.rows_processed,1))) + '. Oracle may be mis-estimating row counts. Compare E-Rows vs A-Rows in plan, gather stats with DBMS_STATS.GATHER_TABLE_STATS + METHOD_OPT=>\'FOR ALL COLUMNS SIZE AUTO\''});
        }
        if (s.epe > 1 && s.executions > 1000 && s.gpe > 10000) {
            hints.push({icon:'\u{2699}', text:'MATERIALIZATION CANDIDATE: ' + comma(s.executions) + ' execs x ' + num(s.epe,2) + 's/exec. If this SQL repeatedly aggregates the same data, consider pre-materializing results into a staging table or Materialized View.'});
        }
        if (s.executions > 500000) {
            hints.push({icon:'\u26A0', text:'PARSE OVERHEAD: ' + comma(s.executions) + ' executions. Verify cursor reuse: parse_calls vs executions in V$SQL. If 1:1 ratio, add bind variables or set CURSOR_SHARING=FORCE.'});
        }
