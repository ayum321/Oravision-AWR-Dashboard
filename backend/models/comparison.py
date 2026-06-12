"""Pydantic models for AWR comparison results."""
from __future__ import annotations
from pydantic import BaseModel, Field, computed_field
from typing import Literal, Optional

# Shared severity type — single definition reused across all models
SeverityLevel = Literal["critical", "warning", "info", "good"]

# Shared classification type for wait events
WaitClassification = Literal["new_bottleneck", "worsening", "improving", "stable", ""]

# Shared assessment type for SQL regressions
NetAssessment = Literal[
    "Regressed", "Stable", "Improved", "New SQL", "Disappeared", "Cannot Determine"
]


class MetricDelta(BaseModel):
    metric: str
    good_value: float = 0.0
    bad_value: float = 0.0
    good_per_txn: float = 0.0
    bad_per_txn: float = 0.0
    change_pct: float = 0.0
    direction: Literal["regression", "improvement", "stable"] = "stable"
    severity: SeverityLevel = "info"

    @computed_field
    @property
    def delta_pct(self) -> float:
        """Backward-compatible alias used by older dashboard consumers."""
        return self.change_pct


class WaitEventComparison(BaseModel):
    event_name: str
    good_time_secs: float = 0.0
    bad_time_secs: float = 0.0
    good_pct_db_time: float = 0.0
    bad_pct_db_time: float = 0.0
    delta_pct: float = 0.0
    delta_pct_db_time: float = 0.0   # bad_pct - good_pct (absolute, not relative)
    wait_class: str = "Other"
    classification: WaitClassification = ""  # typed, not free string
    root_cause_hint: str = ""
    pathology_meaning: str = ""      # from PATHOLOGY_MAP
    pathology_investigate: list[str] = Field(default_factory=list)
    causal_parents: list[str] = Field(default_factory=list)
    causal_children: list[str] = Field(default_factory=list)
    # Per-event latency
    good_total_waits: int = 0
    bad_total_waits: int = 0
    good_avg_wait_ms: float = 0.0
    bad_avg_wait_ms: float = 0.0
    latency_delta_pct: float = 0.0
    latency_flag: str = ""  # "" | "volume_increase" | "latency_increase" | "both"
    # Single extreme wait
    good_implied_max_ms: float = 0.0
    bad_implied_max_ms: float = 0.0
    extreme_wait_flag: bool = False
    # Confidence score (0.0–1.0) and z-score vs good period
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    zscore: float = Field(default=0.0, ge=-20.0, le=20.0)
    is_new_dominant: bool = False
    is_disappeared: bool = False     # present in good but absent from bad
    proportionality_note: str = ""  # set when commit/log-file-sync is proportional to workload change


class EfficiencyComparison(BaseModel):
    metric: str
    good_val: float = 0.0
    bad_val: float = 0.0
    delta: float = 0.0
    threshold: str = ""
    message: str = ""
    severity: SeverityLevel = "info"


class SqlRegression(BaseModel):
    sql_id: str
    sql_text_truncated: str = ""
    sql_text_full: str = ""           # full text from SQL Text section
    text_verified: bool = False       # cross-validation passed
    tables_referenced: list[str] = Field(default_factory=list)
    sql_module: str = ""
    sql_action: str = ""   # AWR SQL statistics Action column
    # IMP2 — oracle maintenance flag
    source_category: str = ""  # "Application" | "Oracle Maintenance" | "Ad-hoc / DBA" | module name
    is_oracle_maintenance: bool = False
    addm_referenced: bool = False     # referenced by ADDM finding
    tag: str = "stable"  # new_offender | regression | load_increase | improved | stable
    good_elapsed_secs: float = 0.0
    bad_elapsed_secs: float = 0.0
    good_avg_elapsed: float = 0.0
    bad_avg_elapsed: float = 0.0
    good_executions: int = 0
    bad_executions: int = 0
    good_cpu_secs: float = 0.0
    bad_cpu_secs: float = 0.0
    good_buffer_gets: float = 0.0
    bad_buffer_gets: float = 0.0
    good_disk_reads: float = 0.0
    bad_disk_reads: float = 0.0
    good_rows_processed: int = 0
    bad_rows_processed: int = 0
    good_rows_per_exec: float = 0.0
    bad_rows_per_exec: float = 0.0
    good_plan_hash: str = ""
    bad_plan_hash: str = ""
    plan_changed: bool = False
    # IMP3 — plan change verdict separate from regression
    plan_verdict: str = ""  # "" | "PLAN CHANGED — REGRESSED" | "PLAN CHANGED — IMPROVED" | "PLAN CHANGED — STABLE"
    # IMP10 — net assessment (typed Literal, not free string)
    net_assessment: NetAssessment = "Cannot Determine"
    net_assessment_detail: str = ""
    delta_pct: float = 0.0
    exec_delta_pct: float = 0.0
    avg_elapsed_delta_pct: float = 0.0
    severity: SeverityLevel = "info"
    # IMP1 — normalized rates
    good_elapsed_per_min: float = 0.0
    bad_elapsed_per_min: float = 0.0
    good_execs_per_min: float = 0.0
    bad_execs_per_min: float = 0.0
    # CPU/IO breakdown
    cpu_pct: float = 0.0   # % of elapsed that is CPU
    io_pct: float = 0.0    # % of elapsed that is I/O
    # Phase 4 — regression score (bad_avg/good_avg * log10(executions))
    regression_score: float = 0.0
    # Phase 4 — wait absorption (CPU dropped while elapsed rose = blocked on waits)
    wait_absorption: bool = False
    wait_absorption_note: str = ""


class Recommendation(BaseModel):
    priority: int = 3  # 1=critical, 2=high, 3=medium
    category: str = ""  # Memory | SQL | I/O | Concurrency | Configuration
    finding: str = ""
    action: str = ""
    oracle_fix: str = ""
    impact: str = ""
    reference: str = ""


class PeriodSummary(BaseModel):
    label: str = ""
    snap_begin: int = 0
    snap_end: int = 0
    db_time_secs: float = 0.0
    elapsed_secs: float = 0.0
    elapsed_min: float = 0.0
    aas: float = 0.0
    # IMP7 — txn/sec primary KPI
    txn_per_sec: float = 0.0
    txn_per_sec_available: bool = False
    db_time_per_min: float = 0.0
    parses_per_min: float = 0.0
    parses_per_min_available: bool = False


class ComparisonSummary(BaseModel):
    good_period: PeriodSummary = Field(default_factory=PeriodSummary)
    bad_period: PeriodSummary = Field(default_factory=PeriodSummary)
    health_score_good: int = 100
    health_score_bad: int = 100
    overall_regression: str = ""
    severity: Literal["healthy", "degraded", "critical"] = "healthy"
    # IMP7 — congestion indicator
    congestion_signal: bool = False
    congestion_message: str = ""
    # Phase 6 — ratio inversion (txn/s down + DB time/s up = wait-loop congestion)
    ratio_inversion: bool = False
    ratio_inversion_score: float = 0.0   # 0.0–1.0 severity weight
    # Phase 8 — causal chain text
    causal_chain_text: str = ""
    # Evidence-based headline
    headline: str = ""
    headline_evidence: list[str] = Field(default_factory=list)
    # Bottleneck type
    good_bottleneck: str = ""  # "CPU" | "I/O" | "Concurrency" | "Mixed"
    bad_bottleneck: str = ""
    bottleneck_shift: str = ""  # "" | "CPU→I/O" | unchanged | etc.
    # Key metrics for quick display
    db_time_delta_pct: float = 0.0
    exec_rate_delta_pct: float = 0.0
    aas_good: float = 0.0
    aas_bad: float = 0.0
    cpu_capacity_used_pct: float = 0.0  # AAS / num_cpus * 100


class NormalizedMetric(BaseModel):
    """A single pre-computed comparison metric — the canonical unit in normalized_comparison."""
    key: str = ""                   # machine key e.g. "physical_reads"
    label: str = ""                 # human label e.g. "Physical Reads/sec"
    group: str = ""                 # "load_profile" | "efficiency" | "workload" | "wait"
    good_val: float = 0.0
    bad_val: float = 0.0
    unit: str = ""                  # "/sec" | "%" | "min" | "ms" etc.
    delta_pct: float = 0.0
    direction: str = "stable"       # "regression" | "improvement" | "stable" | "new"
    severity: str = "info"          # "critical" | "warning" | "info" | "good"
    is_significant: bool = False    # |delta_pct| >= significance threshold
    higher_is_bad: bool = True      # for direction coloring
    explanation: str = ""           # one-line Oracle DBA explanation


class NormalizedComparison(BaseModel):
    """
    Single source of truth for all comparison metrics.
    Built once by compare_periods(), consumed by every dashboard section.
    Stored in the API JSON response as 'normalized_comparison'.
    """
    # Ordered list of ALL metrics — frontend can iterate this instead of recomputing
    all_metrics: list[NormalizedMetric] = Field(default_factory=list)
    # Pre-filtered: only metrics with is_significant=True
    significant: list[NormalizedMetric] = Field(default_factory=list)
    # Canonical category groups (pre-filtered)
    load_profile: list[NormalizedMetric] = Field(default_factory=list)
    efficiency: list[NormalizedMetric] = Field(default_factory=list)
    wait_events: list[NormalizedMetric] = Field(default_factory=list)
    # Summary judgments
    db_time_delta_pct: float = 0.0
    aas_good: float = 0.0
    aas_bad: float = 0.0
    top_regression: str = ""        # label of the metric that regressed most
    top_regression_pct: float = 0.0
    critical_count: int = 0
    warning_count: int = 0


class ComparisonReport(BaseModel):
    summary: ComparisonSummary = Field(default_factory=ComparisonSummary)
    load_profile_delta: list[MetricDelta] = Field(default_factory=list)
    top_wait_events: dict = Field(default_factory=dict)
    instance_efficiency: dict = Field(default_factory=dict)
    sql_regressions: list[SqlRegression] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    incident_indicators: list[dict] = Field(default_factory=list)
    rca_chains: list[dict] = Field(default_factory=list)
    # IMP4 — logon storm explanation
    logon_storm_explanation: str = ""
    # IMP5 — batch groups
    batch_groups: list[dict] = Field(default_factory=list)
    # ADDM findings (authoritative evidence)
    addm_findings: list[dict] = Field(default_factory=list)
    # SQL zones for structured display
    sql_high_frequency: list[SqlRegression] = Field(default_factory=list)   # exec/min > 50
    sql_plan_changes: list[SqlRegression] = Field(default_factory=list)     # plan_hash changed
    sql_new_in_bad: list[SqlRegression] = Field(default_factory=list)       # new_offender only
    sql_maintenance: list[SqlRegression] = Field(default_factory=list)      # oracle maintenance
    # ── Canonical single source of truth (new) ──────────────────────────────
    normalized_comparison: NormalizedComparison = Field(default_factory=NormalizedComparison)
    # ── DBWR Instance Activity Stats comparison (Trigger 3) ─────────────────
    dbwr_activity: dict = Field(default_factory=dict)
