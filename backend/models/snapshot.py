"""Pydantic models for AWR snapshot data."""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class SnapshotRange(BaseModel):
    snap_id_begin: int
    snap_id_end: int
    label: str = ""


class SnapshotInfo(BaseModel):
    snap_id: int
    begin_time: str
    end_time: str
    duration_mins: float = 0.0


class LoadProfileMetric(BaseModel):
    stat_name: str
    per_sec: float = 0.0
    per_txn: float = 0.0


class WaitEvent(BaseModel):
    event_name: str
    total_waits: int = 0
    time_waited_secs: float = 0.0
    avg_wait_ms: float = 0.0
    pct_db_time: float = 0.0
    wait_class: str = "Other"
    # Normalised category for frontend colouring — populated by html_parser
    wait_class_category: str = ""   # CPU | IO | Concurrency | Lock | Memory | Other


class InstanceEfficiency(BaseModel):
    buffer_cache_hit_pct:  float = 0.0
    library_cache_hit_pct: float = 0.0
    soft_parse_pct:        float = 0.0
    # Oracle AWR documents execute_to_parse_pct as legitimately negative
    # when parse_calls > executions (e.g. shared-pool churn periods)
    execute_to_parse_pct:  float = 0.0
    latch_hit_pct:         float = 0.0

    @field_validator(
        "buffer_cache_hit_pct", "library_cache_hit_pct",
        "soft_parse_pct", "latch_hit_pct",
        mode="before",
    )
    @classmethod
    def _clamp_pct(cls, v) -> float:
        """Clamp to [0, 100]; float rounding in AWR HTML can produce 100.0001 etc."""
        try:
            return max(0.0, min(100.0, float(v or 0)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("execute_to_parse_pct", mode="before")
    @classmethod
    def _clamp_e2p(cls, v) -> float:
        """Execute-to-Parse can be negative — clamp to [-100, 100] only."""
        try:
            return max(-100.0, min(100.0, float(v or 0)))
        except (TypeError, ValueError):
            return 0.0


class AddmFinding(BaseModel):
    finding_name: str
    avg_active_sessions: float = 0.0
    pct_active_sessions: float = 0.0
    task_name: str = ""
    referenced_sql_ids: list[str] = Field(default_factory=list)


class SqlStat(BaseModel):
    sql_id: str
    sql_text: str = ""
    sql_text_full: str = Field(default="")  # from Complete List of SQL Text — no length limit
    sql_text_truncated: str = Field(default="", max_length=500)  # inline table cell
    text_verified: bool = False
    tables_referenced: list[str] = Field(default_factory=list)
    module: str = Field(default="", max_length=256)
    executions: int = 0
    elapsed_time_secs: float = 0.0
    cpu_time_secs: float = 0.0
    disk_reads: int = 0
    buffer_gets: int = 0
    avg_elapsed_secs: float = 0.0
    plan_hash_value: str = ""
    pct_db_time: float = 0.0
    rows_processed: int = 0
    rows_per_exec: float = 0.0
    addm_referenced: bool = False
    source_section: str = "elapsed_time"
    appeared_in: list[str] = Field(default_factory=lambda: ["elapsed_time"])
    elapsed_rank: int = 999

    @field_validator("avg_elapsed_secs", mode="before")
    @classmethod
    def _compute_avg_elapsed(cls, v, info):
        """If avg_elapsed_secs not supplied, compute from elapsed/executions."""
        if v:
            return v
        data = info.data if hasattr(info, 'data') else {}
        elapsed = data.get("elapsed_time_secs", 0) or 0
        execs   = data.get("executions", 1) or 1
        return round(elapsed / max(execs, 1), 6)


class OsStats(BaseModel):
    num_cpus: int = 0
    cpu_busy_pct: float = 0.0
    iowait_pct: float = 0.0
    phys_mem_gb: float = 0.0
    free_mem_gb: float = 0.0


class TimeModelStat(BaseModel):
    stat_name: str
    time_secs: float = 0.0
    pct_db_time: float = 0.0


class AshSummary(BaseModel):
    session_state: str
    wait_class: str = ""
    event: str = ""
    sample_count: int = 0
    pct: float = 0.0


class SgaComponent(BaseModel):
    component: str
    current_size_mb: float = 0.0
    min_size_mb: float = 0.0
    max_size_mb: float = 0.0


class SegmentStat(BaseModel):
    object_name: str
    object_type: str = ""
    owner: str = ""
    tablespace_name: str = ""
    # Read metrics
    logical_reads: int = 0
    logical_reads_pct: float = 0.0
    physical_reads: int = 0
    physical_reads_pct: float = 0.0
    phys_read_requests: int = 0
    phys_read_requests_pct: float = 0.0
    direct_reads: int = 0
    direct_reads_pct: float = 0.0
    unoptimized_reads: int = 0
    unoptimized_reads_pct: float = 0.0
    optimized_reads: int = 0
    optimized_reads_pct: float = 0.0
    # Write metrics
    physical_writes: int = 0
    physical_writes_pct: float = 0.0
    phys_write_requests: int = 0
    phys_write_requests_pct: float = 0.0
    direct_writes: int = 0
    direct_writes_pct: float = 0.0
    # Cache & activity
    buffer_gets: int = 0
    buffer_gets_pct: float = 0.0
    table_scans: int = 0
    table_scans_pct: float = 0.0
    db_block_changes: int = 0
    db_block_changes_pct: float = 0.0
    # Contention
    row_lock_waits: int = 0
    row_lock_waits_pct: float = 0.0
    itl_waits: int = 0
    itl_waits_pct: float = 0.0
    buffer_busy_waits: int = 0
    buffer_busy_waits_pct: float = 0.0


class AWRData(BaseModel):
    """Complete AWR data for a snapshot range."""
    db_name: str = ""
    db_id: str = ""
    instance: str = ""
    release: str = ""
    host: str = ""
    cpus: int = 1
    memory_gb: float = 0.0
    platform: str = ""
    rac: str = "NO"
    begin_snap: int = 0
    end_snap: int = 0
    begin_time: str = ""
    end_time: str = ""
    elapsed_min: float = 0.0
    db_time_min: float = 0.0
    sessions_begin: int = 0
    sessions_end: int = 0
    load_profile: list[LoadProfileMetric] = Field(default_factory=list)
    efficiency: InstanceEfficiency = Field(default_factory=InstanceEfficiency)
    efficiency_available: list[str] = Field(default_factory=list)
    wait_events: list[WaitEvent] = Field(default_factory=list)
    time_model: list[TimeModelStat] = Field(default_factory=list)
    sql_stats: list[SqlStat] = Field(default_factory=list)
    os_stats: OsStats = Field(default_factory=OsStats)
    ash_summary: list[AshSummary] = Field(default_factory=list)
    sga: list[SgaComponent] = Field(default_factory=list)
    segments: list[SegmentStat] = Field(default_factory=list)
    addm_findings: list[AddmFinding] = Field(default_factory=list)
