"""Regression coverage for the trust-critical stabilization fixes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.comparison import MetricDelta
from routers.rag import _resolve_pdf_upload_path
from services.comparator import compare_periods
from services.data_source import clear_uploaded_data, normalize_upload_label, store_uploaded_data
from services.health_scorer import calculate_health_score
from services.html_parser import _parse_sql_stats, normalize_parsed_data
from services.html_sanitizer import sanitize_html_fragment
from services.rag_narrative import _template_narrative


def _period(**overrides):
    base = {
        "elapsed_min": 60,
        "db_time_min": 1,
        "cpus": 4,
        "load_profile": [],
        "wait_events": [],
        "efficiency": {},
        "sql_stats": [],
        "time_model": [],
        "os_stats": {},
    }
    return {**base, **overrides}


def test_complete_sql_text_uses_structured_table_mapping():
    html = """
    <table summary="sql ordered by elapsed time">
      <tr><th>SQL Id</th><th>Elapsed Time (s)</th><th>SQL Text</th></tr>
      <tr><td>atd87px4a8k25</td><td>10</td><td>SELECT /* inline */</td></tr>
    </table>
    <h3>Complete List of SQL Text</h3>
    <table>
      <tr><th>SQL Id</th><th>SQL Text</th></tr>
      <tr><td><a name="atd87px4a8k25">atd87px4a8k25</a></td>
          <td>SELECT id FROM my_table WHERE id = :b1</td></tr>
    </table>
    """
    entries, _ = _parse_sql_stats(BeautifulSoup(html, "html.parser"))
    assert entries[0]["sql_text"] == "SELECT id FROM my_table WHERE id = :b1"
    assert entries[0]["tables_referenced"] == ["MY_TABLE"]


def test_high_volume_new_sql_is_not_hidden_by_low_per_exec_latency():
    bad = _period(
        db_time_min=900,
        sql_stats=[{
            "sql_id": "newfastsql1234",
            "elapsed_time_secs": 50000,
            "cpu_time_secs": 10000,
            "executions": 100000,
            "avg_elapsed_secs": 0.5,
        }],
    )
    regression = compare_periods(_period(), bad).sql_regressions[0]
    assert regression.tag == "new_offender"
    assert regression.severity == "critical"
    assert regression.regression_score > 1000


def test_missing_efficiency_is_skipped_after_normalization():
    health = calculate_health_score(normalize_parsed_data({}).model_dump())
    assert health["score"] == 100
    assert health["alerts"] == []
    assert any("data unavailable" in check for check in health["skipped_checks"])


def test_comparison_skips_missing_efficiency_instead_of_inventing_zeroes():
    good = _period(
        efficiency={"buffer_cache_hit_pct": 99.5},
        efficiency_available=["buffer_cache_hit_pct"],
    )
    bad = _period(efficiency={}, efficiency_available=[])
    comparison = compare_periods(good, bad)
    assert comparison.instance_efficiency["comparisons"] == []
    assert not [
        metric for metric in comparison.normalized_comparison.efficiency
        if metric.key == "buffer_cache_hit_pct"
    ]


def test_comparison_skips_omitted_load_profile_but_keeps_measured_zero():
    good = _period(load_profile=[{"stat_name": "Parse Count (Total):", "per_sec": 10}])
    missing = compare_periods(good, _period())
    assert missing.load_profile_delta == []
    assert not [
        metric for metric in missing.normalized_comparison.load_profile
        if metric.key == "parses"
    ]

    measured_zero = compare_periods(
        good,
        _period(load_profile=[{"stat_name": "Parse Count (Total):", "per_sec": 0}]),
    )
    assert measured_zero.load_profile_delta[0].change_pct == -100
    assert any(
        metric.key == "parses" and metric.delta_pct == -100
        for metric in measured_zero.normalized_comparison.load_profile
    )


def test_logon_storm_requires_execute_to_parse_evidence():
    comparison = compare_periods(
        _period(load_profile=[{"stat_name": "Logons:", "per_sec": 1}]),
        _period(load_profile=[{"stat_name": "Logons:", "per_sec": 10}]),
    )
    assert comparison.logon_storm_explanation == ""


def test_missing_transaction_rate_does_not_create_throughput_collapse():
    comparison = compare_periods(
        _period(
            db_time_min=10,
            load_profile=[
                {"stat_name": "Transactions:", "per_sec": 10},
                {"stat_name": "Executes:", "per_sec": 100},
            ],
        ),
        _period(db_time_min=30),
    )
    assert comparison.summary.ratio_inversion is False
    assert comparison.summary.exec_rate_delta_pct == 0
    assert not [
        metric for metric in comparison.normalized_comparison.all_metrics
        if metric.key == "txn_per_sec"
    ]


def test_cpu_capacity_uses_problem_period_cpu_count():
    comparison = compare_periods(
        _period(cpus=16),
        _period(cpus=2, db_time_min=240),
    )
    assert comparison.summary.cpu_capacity_used_pct == 200


def test_top_level_cpu_count_participates_in_aas_scoring():
    health = calculate_health_score(_period(
        load_profile=[{"stat_name": "DB Time(s):", "per_sec": 10}],
    ))
    assert any(alert["metric"] == "AAS/CPU Ratio" for alert in health["alerts"])


def test_legacy_delta_alias_remains_available_in_attributes_and_json():
    delta = MetricDelta(metric="Executes", change_pct=42.5)
    assert delta.delta_pct == 42.5
    assert delta.model_dump()["delta_pct"] == 42.5


def test_rag_html_sanitizer_removes_active_content_and_attributes():
    html = '<script>alert(1)</script><p onclick="alert(2)">Safe <b>text</b></p>'
    assert sanitize_html_fragment(html) == "<p>Safe <b>text</b></p>"


def test_upload_labels_are_bounded_and_normalized():
    clear_uploaded_data()
    assert normalize_upload_label(" Report_01 ") == "report_01"
    with pytest.raises(ValueError):
        store_uploaded_data("../../escape", {})


def test_pdf_ingestion_requires_a_filename_without_path_components():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_pdf_upload_path("../../secret.pdf")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Provide a PDF filename only."


def test_pdf_cross_check_snippets_are_escaped_before_render(monkeypatch):
    monkeypatch.setattr(
        "services.pdf_kb.cross_check_rca",
        lambda **kwargs: [{
            "source_file": "<img src=x onerror=alert(1)>",
            "page_num": 1,
            "section": "<script>alert(2)</script>",
            "chunk_text": "<b onclick=alert(3)>unsafe</b>",
        }],
    )
    narrative = _template_narrative(
        {"lbl1": "<script>baseline</script>", "lbl2": "problem"},
        {},
        [],
        "",
    )
    assert "<script>" not in narrative
    assert "<img" not in narrative
    assert "&lt;img src=x onerror=alert(1)&gt;" in narrative
    assert "&lt;b onclick=alert(3)&gt;unsafe&lt;/b&gt;" in narrative


def test_inline_dashboard_escapes_error_text_before_html_insertion():
    template = (
        Path(__file__).parent.parent / "backend" / "templates" / "index.html"
    ).read_text(encoding="utf-8")
    assert "${esc(e.message)}" in template
    assert "+esc(hint)+'</div>'" in template
    assert "${esc(detail)}</span>" in template
    assert "${esc(where)} FAILED:</strong> ${esc(e.message)}" in template
    assert "${esc(name)}</span>`+" in template
