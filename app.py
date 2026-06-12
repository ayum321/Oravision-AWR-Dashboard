"""
OraVision AWR Pro — Streamlit Deployment App
=============================================
Deployable to Streamlit Community Cloud (or any server) from a private
GitHub repository.  Source code never leaves your repo.

Run locally:  streamlit run app.py
Deploy:       Push to private GitHub → connect on share.streamlit.io
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime
from io import StringIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Runtime path setup ─────────────────────────────────────────────────────
# Resolves imports for services/ and models/ inside backend/
_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from services.comparator import compare_periods          # noqa: E402
from services.health_scorer import (                      # noqa: E402
    build_health_checks,
    calculate_health_score,
)
from services.html_parser import parse_awr_html           # noqa: E402
from services.rca_engine import run_rca                   # noqa: E402

# ── Page configuration ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="OraVision AWR Pro",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global dark-theme CSS ──────────────────────────────────────────────────
st.markdown(
    """
<style>
/* Base overrides */
[data-testid="stAppViewContainer"] { background:#0b0f1a; }
[data-testid="stSidebar"] { background:#0d1117; border-right:1px solid #1e293b; }
[data-testid="stSidebar"] * { color:#e2e8f0 !important; }
h1,h2,h3,h4 { color:#e2e8f0; }
p, li, span, label { color:#cbd5e1; }
.stTextInput input, .stPasswordInput input {
    background:#111827 !important; color:#e2e8f0 !important;
    border:1px solid #334155 !important; border-radius:8px;
}
[data-testid="stFileUploader"] {
    background:#111827; border:1.5px dashed #334155;
    border-radius:10px; padding:12px;
}
[data-testid="stFileUploader"]:hover { border-color:#06b6d4; }
div[data-testid="stMetric"] {
    background:#111827; border:1px solid #1e293b;
    border-radius:12px; padding:16px;
}
div[data-testid="stMetric"] label { color:#64748b !important; font-size:11px !important; text-transform:uppercase; }
div[data-testid="stMetricValue"] { color:#e2e8f0 !important; }
div[data-testid="stMetricDelta"] > div { font-size:12px !important; }
/* Tab styling */
button[data-baseweb="tab"] { background:transparent !important; color:#94a3b8 !important; }
button[data-baseweb="tab"][aria-selected="true"] {
    background:#164e63 !important; color:#22d3ee !important; border-radius:6px;
}
/* Dataframe */
[data-testid="stDataFrame"] { border:1px solid #1e293b; border-radius:8px; }
/* Expander */
details { background:#111827 !important; border:1px solid #1e293b !important; border-radius:8px; }
/* Alert boxes */
.sev-critical { color:#f87171; font-weight:700; }
.sev-warning  { color:#fbbf24; font-weight:700; }
.sev-good     { color:#34d399; font-weight:700; }
.sev-info     { color:#60a5fa; font-weight:700; }
/* Cards */
.finding-card {
    border-radius:8px; padding:12px 14px; margin-bottom:8px;
    border-left:4px solid; line-height:1.5;
}
.card-critical { background:#450a0a; border-color:#dc2626; }
.card-warning  { background:#451a03; border-color:#d97706; }
.card-good     { background:#022c22; border-color:#10b981; }
.card-info     { background:#0c1f3d; border-color:#3b82f6; }
/* Sidebar buttons */
[data-testid="stSidebar"] .stButton button {
    width:100%; background:#1e293b; border:1px solid #334155;
    color:#94a3b8; border-radius:8px; font-size:12px;
}
[data-testid="stSidebar"] .stButton button:hover { background:#164e63; color:#22d3ee; border-color:#0891b2; }
/* Login card */
.login-card {
    max-width:420px; margin:80px auto; background:#111827;
    border:1px solid #1e293b; border-radius:14px; padding:36px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def _check_login(username: str, password: str) -> bool:
    """Validate against st.secrets or fallback env vars."""
    try:
        users: dict = st.secrets["credentials"]["users"]
    except (KeyError, AttributeError):
        # Allow override via env for local testing:  ORAVISION_USERS="admin:secret,tester:pass"
        raw = os.getenv("ORAVISION_USERS", "")
        users = {}
        for pair in raw.split(","):
            if ":" in pair:
                u, p = pair.split(":", 1)
                users[u.strip()] = _hash(p.strip())

    if not users:
        st.error("No credentials configured. Add [credentials] section to .streamlit/secrets.toml")
        return False

    stored = users.get(username, "")
    # Accept pre-hashed SHA-256 OR plain-text values (auto-hashed at runtime)
    pwd_hash = _hash(password)
    return stored == pwd_hash or stored == password


def login_gate() -> bool:
    """Render login form and return True only when authenticated."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style="text-align:center;margin-top:60px">
            <div style="font-size:2.8rem;font-weight:900;background:linear-gradient(135deg,#fff 0%,#06b6d4 60%,#8b5cf6 100%);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                OraVision AWR Pro
            </div>
            <p style="color:#64748b;margin-top:6px">Oracle AWR Root Cause Analysis Platform</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            st.markdown(
                "<div style='font-size:13px;font-weight:700;color:#94a3b8;text-transform:uppercase;"
                "letter-spacing:1px;margin-bottom:16px'>Sign In</div>",
                unsafe_allow_html=True,
            )
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In →", use_container_width=True)

        if submitted:
            if _check_login(username.strip(), password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.markdown(
        "<p style='text-align:center;color:#334155;font-size:11px;margin-top:40px'>"
        "Access restricted to authorised testers only.</p>",
        unsafe_allow_html=True,
    )
    return False


# ══════════════════════════════════════════════════════════════════════════════
# HELPER RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

def _fmt(v, decimals=1) -> str:
    if v is None:
        return "–"
    try:
        f = float(v)
        if decimals == 0:
            return f"{f:,.0f}"
        return f"{f:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(v)


def _delta_pct(good, bad) -> str:
    try:
        g, b = float(good), float(bad)
        if g == 0:
            return "–"
        d = (b - g) / abs(g) * 100
        sign = "+" if d > 0 else ""
        return f"{sign}{d:.0f}%"
    except (ValueError, TypeError):
        return "–"


def _sev_color(sev: str) -> str:
    return {"critical": "#f87171", "warning": "#fbbf24", "good": "#34d399",
            "info": "#60a5fa", "healthy": "#34d399", "degraded": "#fbbf24"}.get(sev, "#94a3b8")


def _sev_emoji(sev: str) -> str:
    return {"critical": "🔴", "warning": "🟡", "good": "🟢", "info": "🔵",
            "healthy": "🟢", "degraded": "🟡"}.get(sev, "⚪")


def render_health_score_card(score: int, grade: str, severity: str, label: str):
    color = _sev_color(severity)
    st.markdown(
        f"""
        <div style="background:#111827;border:1px solid #1e293b;border-radius:12px;
                    padding:20px;text-align:center">
            <div style="font-size:10px;color:#64748b;text-transform:uppercase;
                        letter-spacing:1px;margin-bottom:8px">{label}</div>
            <div style="font-size:3rem;font-weight:900;color:{color};line-height:1">{score}</div>
            <div style="font-size:1.2rem;font-weight:700;color:{color};margin-top:4px">Grade {grade}</div>
            <div style="font-size:11px;color:{color};margin-top:4px;text-transform:uppercase">{severity}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_finding_card(title: str, detail: str, severity: str, evidence_from: str = ""):
    css_cls = {"critical": "card-critical", "warning": "card-warning",
               "good": "card-good", "info": "card-info"}.get(severity, "card-info")
    emoji = _sev_emoji(severity)
    st.markdown(
        f"""
        <div class="finding-card {css_cls}">
            <div style="font-size:13px;font-weight:700;color:#e2e8f0">{emoji} {title}</div>
            <div style="font-size:12px;color:#94a3b8;margin-top:4px">{detail}</div>
            {f'<div style="font-size:10px;color:#475569;margin-top:4px">{evidence_from}</div>' if evidence_from else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_wait_events_chart(events: list[dict], title: str, color: str = "#06b6d4"):
    if not events:
        st.info("No wait event data available.")
        return
    top = sorted(events, key=lambda e: e.get("pct_db_time", 0), reverse=True)[:12]
    names = [e.get("event_name", "Unknown") for e in top]
    pcts = [e.get("pct_db_time", 0) for e in top]
    # Truncate long names
    names = [n if len(n) <= 28 else n[:26] + "…" for n in names]
    fig = go.Figure(go.Bar(
        x=pcts,
        y=names,
        orientation="h",
        marker=dict(color=color, opacity=0.85),
        text=[f"{p:.1f}%" for p in pcts],
        textposition="outside",
        textfont=dict(size=11, color="#94a3b8"),
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#94a3b8"), x=0),
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=max(300, len(top) * 34 + 80),
        margin=dict(l=10, r=60, t=40, b=20),
        xaxis=dict(showgrid=True, gridcolor="#1e293b", color="#475569",
                   ticksuffix="%", range=[0, max(pcts) * 1.18] if pcts else [0, 100]),
        yaxis=dict(autorange="reversed", color="#94a3b8", tickfont=dict(size=11)),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_wait_comparison_chart(ev1: list, ev2: list, lbl1: str, lbl2: str):
    all_names = sorted({e.get("event_name", "") for e in ev1 + ev2} - {""})
    map1 = {e["event_name"]: e.get("pct_db_time", 0) for e in ev1 if "event_name" in e}
    map2 = {e["event_name"]: e.get("pct_db_time", 0) for e in ev2 if "event_name" in e}
    # Only show events that have data in at least one period and have non-zero values
    names = [n for n in all_names if map1.get(n, 0) > 0 or map2.get(n, 0) > 0]
    names = sorted(names, key=lambda n: max(map1.get(n, 0), map2.get(n, 0)), reverse=True)[:14]
    short_names = [n if len(n) <= 30 else n[:28] + "…" for n in names]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=lbl1, x=[map1.get(n, 0) for n in names], y=short_names,
        orientation="h", marker_color="rgba(52,211,153,0.75)",
        text=[f"{map1.get(n,0):.1f}%" for n in names],
        textposition="inside", textfont=dict(size=10),
    ))
    fig.add_trace(go.Bar(
        name=lbl2, x=[map2.get(n, 0) for n in names], y=short_names,
        orientation="h", marker_color="rgba(248,113,113,0.75)",
        text=[f"{map2.get(n,0):.1f}%" for n in names],
        textposition="inside", textfont=dict(size=10),
    ))
    fig.update_layout(
        barmode="group",
        title=dict(text=f"Wait Events: {lbl1} vs {lbl2}", font=dict(size=13, color="#94a3b8"), x=0),
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=max(380, len(names) * 50 + 80),
        margin=dict(l=10, r=40, t=40, b=20),
        xaxis=dict(showgrid=True, gridcolor="#1e293b", color="#475569", ticksuffix="%"),
        yaxis=dict(autorange="reversed", color="#94a3b8", tickfont=dict(size=11)),
        legend=dict(bgcolor="#111827", bordercolor="#1e293b", borderwidth=1,
                    font=dict(color="#94a3b8", size=11)),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_efficiency_bars(eff: dict, label: str):
    metrics = [
        ("Buffer Cache Hit %", eff.get("buffer_cache_hit_pct", 0), 95),
        ("Soft Parse %",        eff.get("soft_parse_pct", 0),        95),
        ("Library Cache Hit %", eff.get("library_cache_hit_pct", 0), 97),
        ("Execute to Parse %",  eff.get("execute_to_parse_pct", 0),  70),
        ("Latch Hit %",         eff.get("latch_hit_pct", 0),         99),
    ]
    st.markdown(f"**{label}**")
    for name, val, thresh in metrics:
        color = "#10b981" if val >= thresh else ("#f59e0b" if val >= thresh * 0.95 else "#ef4444")
        st.markdown(
            f"""
            <div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                <span style="font-size:12px;color:#94a3b8">{name}</span>
                <span style="font-size:12px;font-weight:700;color:{color}">{val:.1f}%</span>
              </div>
              <div style="background:#1e293b;border-radius:4px;height:8px">
                <div style="width:{min(val,100):.1f}%;background:{color};height:8px;border-radius:4px"></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE AWR VIEW
# ══════════════════════════════════════════════════════════════════════════════

def render_single_awr(data: dict, label: str):
    rca = run_rca(data)
    health = calculate_health_score(data)
    checks = build_health_checks(data)

    db = rca.get("db_summary", {})
    verdict = rca.get("verdict", {})
    findings = rca.get("findings", [])
    trail = rca.get("investigation_trail", [])
    remediations = rca.get("remediations", [])

    # ── DB Info Banner ─────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f172a,#1a1a2e);border:1px solid #2d3748;
                    border-radius:12px;padding:16px 24px;margin-bottom:16px">
            <div style="font-size:1.4rem;font-weight:900;color:#22d3ee;margin-bottom:6px">
                🗄 {db.get('db_name','Unknown')}
                <span style="font-size:12px;color:#64748b;font-weight:400;margin-left:12px">
                    {db.get('instance','')}
                </span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:20px;margin-top:4px">
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">Release</b>&nbsp;&nbsp;{db.get('release','–')}
                </span>
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">Host</b>&nbsp;&nbsp;{db.get('host','–')}
                </span>
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">CPUs</b>&nbsp;&nbsp;{db.get('cpus','–')}
                </span>
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">Memory</b>&nbsp;&nbsp;{db.get('memory_gb','–')} GB
                </span>
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">Snaps</b>&nbsp;&nbsp;{db.get('snap_begin','–')} → {db.get('snap_end','–')}
                </span>
                <span style="font-size:12px;color:#94a3b8">
                    <b style="color:#64748b">Period</b>&nbsp;&nbsp;{db.get('begin_time','–')} → {db.get('end_time','–')}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["🏠 Overview", "⏳ Wait Events", "🔍 RCA Findings", "📋 SQL Stats",
                    "✅ Health Checks", "🛠 Remediations"])

    # ── Tab 1: Overview ───────────────────────────────────────────────────
    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        cpus = db.get("cpus", 1) or 1
        aas = db.get("aas", 0)
        aas_color = "inverse" if aas > cpus else "normal"

        with c1:
            render_health_score_card(health["score"], health["grade"], health["severity"], label)
        with c2:
            st.metric("Avg Active Sessions (AAS)",
                      f"{aas:.1f}",
                      delta=f"{cpus} CPUs — {'⚠ SATURATED' if aas > cpus else 'OK'}",
                      delta_color=aas_color)
        with c3:
            db_min = round(db.get("db_time_secs", 0) / 60, 1)
            st.metric("DB Time (min)", f"{db_min}")
        with c4:
            el_min = round(db.get("elapsed_secs", 0) / 60, 1)
            st.metric("Elapsed (min)", f"{el_min}")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Verdict
        primary = verdict.get("primary_finding", "")
        root_cause = verdict.get("root_cause", "")
        confidence = verdict.get("confidence", 0)
        conf_color = "#34d399" if confidence >= 80 else ("#fbbf24" if confidence >= 50 else "#f87171")
        if primary:
            st.markdown(
                f"""
                <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b,#312e81,#0f172a);
                            border:1px solid #3730a3;border-radius:12px;padding:24px;margin-bottom:12px">
                    <div style="font-size:10px;color:#818cf8;text-transform:uppercase;
                                letter-spacing:1px;margin-bottom:8px">RCA Verdict</div>
                    <div style="font-size:1.1rem;font-weight:800;color:#e2e8f0;margin-bottom:6px">
                        {primary}
                    </div>
                    <div style="font-size:13px;color:#94a3b8;margin-bottom:10px">{root_cause}</div>
                    <div style="font-size:11px;color:{conf_color};font-weight:700">
                        Confidence: {confidence}%
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Efficiency bars
        eff = data.get("efficiency", {})
        if isinstance(eff, dict):
            render_efficiency_bars(eff, "Instance Efficiency")

    # ── Tab 2: Wait Events ────────────────────────────────────────────────
    with tabs[1]:
        wait_events = data.get("wait_events", [])
        render_wait_events_chart(wait_events, f"Top Wait Events — {label}")
        if wait_events:
            df = pd.DataFrame(wait_events)
            cols = [c for c in ["event_name", "total_waits", "time_waited_secs",
                                 "avg_wait_ms", "pct_db_time", "wait_class"] if c in df.columns]
            df_show = df[cols].sort_values("pct_db_time", ascending=False).reset_index(drop=True)
            df_show.columns = [c.replace("_", " ").title() for c in df_show.columns]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Tab 3: RCA Findings ───────────────────────────────────────────────
    with tabs[2]:
        if findings:
            for sev in ("critical", "warning", "info"):
                group = [f for f in findings if f.get("severity") == sev]
                if group:
                    st.markdown(
                        f"<div style='font-size:11px;font-weight:700;color:{_sev_color(sev)};"
                        f"text-transform:uppercase;letter-spacing:1px;margin:12px 0 6px'>■ {sev} ({len(group)})</div>",
                        unsafe_allow_html=True,
                    )
                    for f in group:
                        render_finding_card(
                            f.get("title", ""),
                            f.get("detail", ""),
                            sev,
                            f.get("evidence_from", ""),
                        )
            # Investigation trail
            if trail:
                st.markdown("---")
                st.markdown("**Investigation Trail**")
                for step in trail:
                    sev = step.get("severity", "info")
                    emoji = _sev_emoji(sev)
                    with st.expander(
                        f"{emoji} Step {step.get('step_num','')}: {step.get('section','')}"
                    ):
                        st.markdown(
                            f"<div style='font-size:13px;color:#e2e8f0;font-weight:600'>"
                            f"{step.get('finding','')}</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"<div style='font-size:12px;color:#94a3b8;margin-top:6px'>"
                            f"{step.get('interpretation','')}</div>",
                            unsafe_allow_html=True,
                        )
        else:
            st.info("No significant findings detected.")

    # ── Tab 4: SQL Stats ──────────────────────────────────────────────────
    with tabs[3]:
        sql_stats = data.get("sql_stats", [])
        if sql_stats:
            df = pd.DataFrame(sql_stats)
            keep = [c for c in ["sql_id", "executions", "elapsed_time_secs", "cpu_time_secs",
                                  "disk_reads", "buffer_gets", "avg_elapsed_secs",
                                  "pct_db_time", "plan_hash_value", "sql_text"] if c in df.columns]
            df_show = df[keep].sort_values("elapsed_time_secs", ascending=False).reset_index(drop=True)
            if "sql_text" in df_show.columns:
                df_show["sql_text"] = df_show["sql_text"].str[:80]
            df_show.columns = [c.replace("_", " ").title() for c in df_show.columns]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info("No SQL statistics available.")

    # ── Tab 5: Health Checks ──────────────────────────────────────────────
    with tabs[4]:
        if checks:
            df = pd.DataFrame(checks)
            keep = [c for c in ["category", "check", "status", "value", "threshold", "detail"] if c in df.columns]
            df_show = df[keep].reset_index(drop=True)
            # Apply row coloring via styler
            def _style_row(row):
                if row.get("status") == "FAIL":
                    return ["background-color:#450a0a"] * len(row)
                elif row.get("status") == "WARN":
                    return ["background-color:#451a03"] * len(row)
                return [""] * len(row)
            st.dataframe(
                df_show.style.apply(_style_row, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No health check data available.")

    # ── Tab 6: Remediations ───────────────────────────────────────────────
    with tabs[5]:
        if remediations:
            for i, rem in enumerate(remediations[:20], 1):
                sev = "critical" if rem.get("priority") == 1 else "warning"
                with st.expander(
                    f"{_sev_emoji(sev)} P{rem.get('priority',2)} [{rem.get('category','')}] "
                    f"{rem.get('title','Recommendation')}"
                ):
                    st.markdown(
                        f"<div style='font-size:13px;color:#e2e8f0'>"
                        f"{rem.get('action','')}</div>",
                        unsafe_allow_html=True,
                    )
                    if rem.get("oracle_cmd"):
                        st.code(rem["oracle_cmd"], language="sql")
                    if rem.get("rationale"):
                        st.markdown(
                            f"<div style='font-size:11px;color:#64748b;margin-top:6px'>"
                            f"{rem['rationale']}</div>",
                            unsafe_allow_html=True,
                        )
        else:
            st.info("No remediation data available.")


# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON VIEW
# ══════════════════════════════════════════════════════════════════════════════

def render_comparison(good_data: dict, bad_data: dict, lbl1: str, lbl2: str):
    # Run analyses
    rca1 = run_rca(good_data)
    rca2 = run_rca(bad_data)
    health1 = calculate_health_score(good_data)
    health2 = calculate_health_score(bad_data)
    comp = compare_periods(good_data, bad_data)
    comp_dict = comp.model_dump()

    db1 = rca1.get("db_summary", {})
    db2 = rca2.get("db_summary", {})
    ev1 = good_data.get("wait_events", [])[:12]
    ev2 = bad_data.get("wait_events", [])[:12]
    eff1 = good_data.get("efficiency", {}) or {}
    eff2 = bad_data.get("efficiency", {}) or {}
    sql_regressions = comp_dict.get("sql_regressions", [])
    delta_findings = comp_dict.get("load_profile_delta", [])
    recommendations = comp_dict.get("recommendations", [])
    incidents = comp_dict.get("incident_indicators", [])

    # ── Header KPI Row ─────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0f172a,#1e1b4b,#312e81,#0f172a);
                    border:1px solid #3730a3;border-radius:14px;padding:24px;margin-bottom:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
                <div>
                    <div style="font-size:10px;color:#4ade80;text-transform:uppercase;letter-spacing:1px">
                        {lbl1} — BASELINE
                    </div>
                    <div style="font-size:1rem;font-weight:700;color:#e2e8f0;margin-top:2px">
                        {db1.get('db_name','–')} / {db1.get('instance','–')}
                    </div>
                    <div style="font-size:11px;color:#64748b">{db1.get('begin_time','–')} → {db1.get('end_time','–')}</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:2rem;font-weight:900;color:#818cf8">VS</div>
                    <div style="font-size:10px;color:#475569">AWR Comparison</div>
                </div>
                <div style="text-align:right">
                    <div style="font-size:10px;color:#f87171;text-transform:uppercase;letter-spacing:1px">
                        {lbl2} — PROBLEM
                    </div>
                    <div style="font-size:1rem;font-weight:700;color:#e2e8f0;margin-top:2px">
                        {db2.get('db_name','–')} / {db2.get('instance','–')}
                    </div>
                    <div style="font-size:11px;color:#64748b">{db2.get('begin_time','–')} → {db2.get('end_time','–')}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI Metrics Row ───────────────────────────────────────────────────
    aas1, aas2 = db1.get("aas", 0), db2.get("aas", 0)
    cpus = db1.get("cpus") or db2.get("cpus") or 1
    dt1 = round(db1.get("db_time_secs", 0) / 60, 1)
    dt2 = round(db2.get("db_time_secs", 0) / 60, 1)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        render_health_score_card(health1["score"], health1["grade"], health1["severity"], lbl1)
    with c2:
        render_health_score_card(health2["score"], health2["grade"], health2["severity"], lbl2)
    with c3:
        st.metric("AAS (Baseline)", f"{aas1:.1f}", delta=f"{cpus} CPUs")
    with c4:
        st.metric("AAS (Problem)", f"{aas2:.1f}",
                  delta=_delta_pct(aas1, aas2),
                  delta_color="inverse" if aas2 > aas1 else "normal")
    with c5:
        st.metric("DB Time — Baseline (min)", f"{dt1}")
    with c6:
        st.metric("DB Time — Problem (min)", f"{dt2}",
                  delta=_delta_pct(dt1, dt2),
                  delta_color="inverse" if dt2 > dt1 else "normal")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Incident Alerts ───────────────────────────────────────────────────
    if incidents:
        st.markdown(
            "<div style='font-size:11px;font-weight:700;color:#f87171;"
            "text-transform:uppercase;letter-spacing:1px;margin-bottom:8px'>"
            "⚠ Incident Indicators</div>",
            unsafe_allow_html=True,
        )
        for inc in incidents:
            render_finding_card(
                inc.get("indicator", "").replace("_", " ").title(),
                inc.get("description", ""),
                inc.get("severity", "warning"),
            )

    tabs = st.tabs([
        "📊 Wait Events", "⚙ Efficiency", "🗃 SQL Regressions",
        "📈 Load Profile Delta", "🔴 Findings", "🛠 Recommendations",
    ])

    # ── Tab 1: Wait Events ────────────────────────────────────────────────
    with tabs[0]:
        render_wait_comparison_chart(ev1, ev2, lbl1, lbl2)
        st.markdown("---")
        wa_list = comp_dict.get("top_wait_events", {}).get("comparisons", [])
        if wa_list:
            df = pd.DataFrame(wa_list)
            keep = [c for c in ["event_name", "good_pct_db_time", "bad_pct_db_time",
                                  "delta_pct", "classification", "root_cause_hint"] if c in df.columns]
            df_show = df[keep].sort_values("bad_pct_db_time", ascending=False).reset_index(drop=True)
            df_show.columns = [c.replace("good_", f"{lbl1} ").replace("bad_", f"{lbl2} ")
                                .replace("_", " ").title() for c in df_show.columns]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Tab 2: Efficiency ─────────────────────────────────────────────────
    with tabs[1]:
        col_a, col_b = st.columns(2)
        with col_a:
            render_efficiency_bars(eff1, f"⬤ {lbl1} (Baseline)")
        with col_b:
            render_efficiency_bars(eff2, f"⬤ {lbl2} (Problem)")
        # Efficiency comparison table
        eff_comps = comp_dict.get("instance_efficiency", {}).get("comparisons", [])
        if eff_comps:
            st.markdown("**Efficiency Comparison**")
            df = pd.DataFrame(eff_comps)
            keep = [c for c in ["metric", "good_val", "bad_val", "delta", "threshold", "severity"] if c in df.columns]
            df_show = df[keep].reset_index(drop=True)
            df_show.columns = [c.replace("good_val", f"{lbl1}").replace("bad_val", f"{lbl2}")
                                .replace("_", " ").title() for c in df_show.columns]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Tab 3: SQL Regressions ────────────────────────────────────────────
    with tabs[2]:
        if sql_regressions:
            # Summary counts
            reg_cnt = sum(1 for r in sql_regressions if r.get("tag") in ("regression", "new_offender"))
            imp_cnt = sum(1 for r in sql_regressions if r.get("tag") == "improved")
            col_x, col_y, col_z = st.columns(3)
            col_x.metric("Regressions / New Offenders", reg_cnt)
            col_y.metric("Improved SQL", imp_cnt)
            col_z.metric("Total Compared", len(sql_regressions))

            for tag, label_tag, sev in [
                ("new_offender", "New Offenders (in Problem only)", "critical"),
                ("regression",   "Regressions (2x+ slower)",        "critical"),
                ("load_increase","Load Increase (more executions)",  "warning"),
                ("improved",     "Improved",                        "good"),
            ]:
                group = [r for r in sql_regressions if r.get("tag") == tag]
                if not group:
                    continue
                st.markdown(
                    f"<div style='font-size:11px;font-weight:700;color:{_sev_color(sev)};"
                    f"text-transform:uppercase;letter-spacing:1px;margin:12px 0 6px'>"
                    f"{_sev_emoji(sev)} {label_tag} ({len(group)})</div>",
                    unsafe_allow_html=True,
                )
                rows = []
                for r in group[:30]:
                    rows.append({
                        "SQL ID": r.get("sql_id", ""),
                        f"{lbl1} Elapsed (s)": round(r.get("good_elapsed_secs", 0), 2),
                        f"{lbl2} Elapsed (s)": round(r.get("bad_elapsed_secs", 0), 2),
                        "Delta %": f"{r.get('delta_pct',0):+.0f}%",
                        f"{lbl1} Execs": r.get("good_executions", 0),
                        f"{lbl2} Execs": r.get("bad_executions", 0),
                        "Plan Changed": "⚠ YES" if r.get("plan_changed") else "–",
                        "SQL": (r.get("sql_text_truncated", "") or "")[:60],
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No SQL regression data available.")

    # ── Tab 4: Load Profile Delta ─────────────────────────────────────────
    with tabs[3]:
        if delta_findings:
            crit = [d for d in delta_findings if d.get("severity") == "critical"]
            warn = [d for d in delta_findings if d.get("severity") == "warning"]
            if crit:
                st.markdown("**Critical Metric Changes**")
                df = pd.DataFrame(crit)
                keep = [c for c in ["metric", "good_value", "bad_value",
                                     "delta_pct", "direction"] if c in df.columns]
                st.dataframe(df[keep].reset_index(drop=True), use_container_width=True, hide_index=True)
            if warn:
                st.markdown("**Warning Metric Changes**")
                df = pd.DataFrame(warn)
                keep = [c for c in ["metric", "good_value", "bad_value",
                                     "delta_pct", "direction"] if c in df.columns]
                st.dataframe(df[keep].reset_index(drop=True), use_container_width=True, hide_index=True)
        else:
            st.info("No significant load profile deltas.")

    # ── Tab 5: Delta Findings ─────────────────────────────────────────────
    with tabs[4]:
        # Combine incident indicators + wait regressions + efficiency alerts
        all_findings = []
        for inc in incidents:
            all_findings.append({
                "title": inc.get("indicator", "").replace("_", " ").title(),
                "detail": inc.get("description", ""),
                "severity": inc.get("severity", "warning"),
                "source": "Incident",
            })
        for wc in comp_dict.get("top_wait_events", {}).get("worsening", []):
            all_findings.append({
                "title": f"Wait Regression: {wc.get('event_name','')}",
                "detail": (f"{lbl1}: {wc.get('good_pct_db_time',0):.1f}% → "
                           f"{lbl2}: {wc.get('bad_pct_db_time',0):.1f}% "
                           f"({wc.get('delta_pct',0):+.0f}%). "
                           f"{wc.get('root_cause_hint','')}"),
                "severity": "critical" if wc.get("bad_pct_db_time", 0) > 20 else "warning",
                "source": "Wait Events",
            })
        for ec in comp_dict.get("instance_efficiency", {}).get("alerts", []):
            all_findings.append({
                "title": f"Efficiency: {ec.get('metric','').replace('_',' ').title()}",
                "detail": ec.get("message", ""),
                "severity": ec.get("severity", "warning"),
                "source": "Efficiency",
            })

        if all_findings:
            for sev in ("critical", "warning", "info"):
                group = [f for f in all_findings if f.get("severity") == sev]
                if group:
                    st.markdown(
                        f"<div style='font-size:11px;font-weight:700;color:{_sev_color(sev)};"
                        f"text-transform:uppercase;letter-spacing:1px;margin:8px 0 4px'>"
                        f"{_sev_emoji(sev)} {sev.upper()} ({len(group)})</div>",
                        unsafe_allow_html=True,
                    )
                    for f in group:
                        render_finding_card(f["title"], f["detail"], sev, f.get("source", ""))
        else:
            st.success("No significant delta findings detected.")

    # ── Tab 6: Recommendations ────────────────────────────────────────────
    with tabs[5]:
        if recommendations:
            for rem in recommendations[:25]:
                p = rem.get("priority", 2)
                sev = "critical" if p == 1 else "warning"
                with st.expander(
                    f"{_sev_emoji(sev)} P{p} [{rem.get('category','')}] {rem.get('finding','')[:80]}"
                ):
                    st.markdown(
                        f"<div style='font-size:13px;color:#e2e8f0;margin-bottom:8px'>"
                        f"<b>Action:</b> {rem.get('action','')}</div>",
                        unsafe_allow_html=True,
                    )
                    if rem.get("oracle_fix"):
                        st.code(rem["oracle_fix"], language="sql")
                    if rem.get("impact"):
                        st.markdown(
                            f"<div style='font-size:11px;color:#64748b'>Impact: {rem['impact']}</div>",
                            unsafe_allow_html=True,
                        )
        else:
            st.info("No recommendations generated.")


# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD REPORT
# ══════════════════════════════════════════════════════════════════════════════

def _build_download_html(
    good_data: dict, bad_data: dict, lbl1: str, lbl2: str,
    health1: dict, health2: dict, comp_dict: dict,
    rca1: dict, rca2: dict,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    db1 = rca1.get("db_summary", {})
    db2 = rca2.get("db_summary", {})
    incidents = comp_dict.get("incident_indicators", [])
    sql_regs = comp_dict.get("sql_regressions", [])
    recs = comp_dict.get("recommendations", [])

    sev_color = {"critical": "#dc2626", "warning": "#d97706", "good": "#10b981", "info": "#3b82f6"}

    ev1 = good_data.get("wait_events", [])[:10]
    ev2 = bad_data.get("wait_events", [])[:10]
    wait_rows = ""
    all_events = sorted({e.get("event_name", "") for e in ev1 + ev2} - {""})
    ev1_map = {e["event_name"]: e for e in ev1 if "event_name" in e}
    ev2_map = {e["event_name"]: e for e in ev2 if "event_name" in e}
    for ev_name in sorted(all_events, key=lambda n: max(
            ev1_map.get(n, {}).get("pct_db_time", 0),
            ev2_map.get(n, {}).get("pct_db_time", 0)), reverse=True)[:14]:
        p1 = ev1_map.get(ev_name, {}).get("pct_db_time", 0)
        p2 = ev2_map.get(ev_name, {}).get("pct_db_time", 0)
        delta = p2 - p1
        delta_str = f"+{delta:.1f}pp" if delta > 0 else f"{delta:.1f}pp"
        row_bg = "#fef2f2" if delta > 5 else ("#f0fdf4" if delta < -2 else "#ffffff")
        wait_rows += (
            f"<tr style='background:{row_bg}'>"
            f"<td>{ev_name}</td><td>{p1:.1f}%</td><td>{p2:.1f}%</td>"
            f"<td style='color:{'#dc2626' if delta > 2 else '#10b981' if delta < -1 else '#374151'};font-weight:700'>"
            f"{delta_str}</td></tr>"
        )

    sql_rows = ""
    for r in [s for s in sql_regs if s.get("tag") in ("regression", "new_offender")][:15]:
        sql_rows += (
            f"<tr><td style='font-family:monospace;font-size:11px'>{r.get('sql_id','')}</td>"
            f"<td>{r.get('tag','').replace('_',' ').title()}</td>"
            f"<td>{r.get('good_elapsed_secs',0):.2f}s</td>"
            f"<td>{r.get('bad_elapsed_secs',0):.2f}s</td>"
            f"<td style='color:#dc2626;font-weight:700'>{r.get('delta_pct',0):+.0f}%</td>"
            f"<td>{'⚠ YES' if r.get('plan_changed') else '–'}</td>"
            f"<td style='font-size:10px;max-width:180px;overflow:hidden;white-space:nowrap'>"
            f"{(r.get('sql_text_truncated','') or '')[:60]}</td></tr>"
        )

    rec_rows = "".join(
        f"<tr><td>P{r.get('priority',2)}</td><td>{r.get('category','')}</td>"
        f"<td style='max-width:220px'>{r.get('finding','')[:80]}</td>"
        f"<td>{r.get('action','')}</td></tr>"
        for r in recs[:20]
    )

    inc_html = "".join(
        f"<div style='padding:10px;margin-bottom:8px;background:{'#fef2f2' if i.get('severity')=='critical' else '#fffbeb'};"
        f"border-left:4px solid {sev_color.get(i.get('severity','warning'),'#d97706')};border-radius:4px'>"
        f"<b>{i.get('indicator','').replace('_',' ').title()}</b><br>"
        f"<span style='font-size:12px;color:#374151'>{i.get('description','')}</span></div>"
        for i in incidents
    )

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>AWR RCA Report — {lbl1} vs {lbl2}</title>
<style>
  body{{font-family:Arial,sans-serif;background:#fff;color:#1a1a1a;margin:0;padding:0;font-size:13px}}
  .page{{max-width:1100px;margin:0 auto;padding:32px 40px}}
  .header{{background:linear-gradient(135deg,#0c4a6e,#1e3a5f);color:#fff;padding:28px 32px;border-radius:10px;margin-bottom:24px}}
  h1{{color:#fff;font-size:22px;margin:0 0 6px}}
  h2{{color:#0c4a6e;font-size:15px;border-bottom:2px solid #0c4a6e;padding-bottom:4px;margin-top:28px}}
  .subtitle{{color:#93c5fd;font-size:12px}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
  .kpi{{border:1px solid #e2e8f0;border-radius:8px;padding:14px;text-align:center}}
  .kpi-label{{font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600;margin-bottom:4px}}
  .kpi-val{{font-size:22px;font-weight:800;color:#0f172a}}
  .kpi-sub{{font-size:11px;color:#94a3b8;margin-top:2px}}
  table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:12px}}
  th{{background:#f1f5f9;padding:8px 12px;text-align:left;font-size:11px;text-transform:uppercase;color:#64748b;font-weight:700}}
  td{{padding:8px 12px;border-bottom:1px solid #f1f5f9}}
  tr:hover{{background:#f8fafc}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:10px;font-weight:700}}
  .b-crit{{background:#fee2e2;color:#dc2626}}
  .b-warn{{background:#fef3c7;color:#d97706}}
  .b-good{{background:#d1fae5;color:#059669}}
  .footer{{margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;
            font-size:11px;color:#94a3b8;text-align:center}}
  @media print{{body{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style>
</head><body><div class="page">

<div class="header">
  <h1>Oracle AWR Root Cause Analysis Report</h1>
  <div class="subtitle">{lbl1} (Baseline) vs {lbl2} (Problem Period) &bull; Generated {now}</div>
  <div style="margin-top:10px;font-size:12px;color:#bfdbfe">
    DB: {db1.get('db_name','–')} &bull; Release: {db1.get('release','–')} &bull;
    Host: {db1.get('host','–')} &bull; CPUs: {db1.get('cpus','–')}
  </div>
</div>

<h2>Executive Summary</h2>
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">{lbl1} Health Score</div>
    <div class="kpi-val" style="color:{'#10b981' if health1['score']>=80 else '#d97706' if health1['score']>=60 else '#dc2626'}">{health1['score']}</div>
    <div class="kpi-sub">Grade {health1['grade']} · {health1['severity'].title()}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">{lbl2} Health Score</div>
    <div class="kpi-val" style="color:{'#10b981' if health2['score']>=80 else '#d97706' if health2['score']>=60 else '#dc2626'}">{health2['score']}</div>
    <div class="kpi-sub">Grade {health2['grade']} · {health2['severity'].title()}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">DB Time — {lbl1}</div>
    <div class="kpi-val">{round(rca1.get('db_summary',{{}}).get('db_time_secs',0)/60,1)}<span style="font-size:14px;font-weight:400"> min</span></div>
    <div class="kpi-sub">Elapsed: {round(rca1.get('db_summary',{{}}).get('elapsed_secs',0)/60,1)} min</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">DB Time — {lbl2}</div>
    <div class="kpi-val">{round(rca2.get('db_summary',{{}}).get('db_time_secs',0)/60,1)}<span style="font-size:14px;font-weight:400"> min</span></div>
    <div class="kpi-sub">Elapsed: {round(rca2.get('db_summary',{{}}).get('elapsed_secs',0)/60,1)} min</div>
  </div>
</div>

{f'<h2>Incident Indicators</h2>{inc_html}' if incidents else ''}

<h2>Top Wait Events Comparison</h2>
<table>
  <tr><th>Event Name</th><th>{lbl1} % DB Time</th><th>{lbl2} % DB Time</th><th>Delta</th></tr>
  {wait_rows}
</table>

{f'<h2>SQL Regressions</h2><table><tr><th>SQL ID</th><th>Tag</th><th>{lbl1} Elapsed</th><th>{lbl2} Elapsed</th><th>Delta %</th><th>Plan Changed</th><th>SQL Text</th></tr>{sql_rows}</table>' if sql_rows else ''}

{f'<h2>Prioritised Recommendations</h2><table><tr><th>Priority</th><th>Category</th><th>Finding</th><th>Action</th></tr>{rec_rows}</table>' if rec_rows else ''}

<div class="footer">
  OraVision AWR Pro &bull; Report generated {now} &bull; For authorised use only
</div>
</div></body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar() -> tuple[str, dict | None, dict | None, str, str]:
    """Render sidebar and return (mode, data1, data2, lbl1, lbl2)."""
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:12px 0 16px">
                <div style="font-size:1.1rem;font-weight:900;color:#22d3ee">OraVision AWR Pro</div>
                <div style="font-size:10px;color:#475569;margin-top:2px">Oracle RCA Engine</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        mode = st.radio(
            "Analysis Mode",
            ["Single AWR Report", "Compare Two AWRs"],
            index=0,
            key="analysis_mode",
        )

        st.markdown("---")

        data1, data2, lbl1, lbl2 = None, None, "Baseline", "Problem"

        if mode == "Single AWR Report":
            st.markdown("**Upload AWR File**")
            f = st.file_uploader("AWR HTML Report", type=["html", "htm"], key="single_upload")
            lbl1 = st.text_input("Period Label", value="AWR Report", key="lbl_single")
            if f is not None:
                with st.spinner("Parsing AWR report…"):
                    try:
                        content = f.read().decode("utf-8", errors="replace")
                        data1 = parse_awr_html(content)
                        st.success(f"Parsed: {data1.get('db_name','?')} — {data1.get('begin_time','')} → {data1.get('end_time','')}")
                    except Exception as ex:
                        st.error(f"Parse error: {ex}")

        else:
            st.markdown("**Baseline AWR (Good Period)**")
            f1 = st.file_uploader("Baseline AWR HTML", type=["html", "htm"], key="comp_upload1")
            lbl1 = st.text_input("Baseline Label", value="Baseline", key="lbl1")

            st.markdown("**Problem AWR (Bad Period)**")
            f2 = st.file_uploader("Problem AWR HTML", type=["html", "htm"], key="comp_upload2")
            lbl2 = st.text_input("Problem Label", value="Problem", key="lbl2")

            if f1 is not None:
                with st.spinner("Parsing baseline…"):
                    try:
                        content1 = f1.read().decode("utf-8", errors="replace")
                        data1 = parse_awr_html(content1)
                        st.success(f"Baseline: {data1.get('db_name','?')}")
                    except Exception as ex:
                        st.error(f"Baseline parse error: {ex}")

            if f2 is not None:
                with st.spinner("Parsing problem period…"):
                    try:
                        content2 = f2.read().decode("utf-8", errors="replace")
                        data2 = parse_awr_html(content2)
                        st.success(f"Problem: {data2.get('db_name','?')}")
                    except Exception as ex:
                        st.error(f"Problem period parse error: {ex}")

        st.markdown("---")

        # Download button (shown when comparison data available)
        if mode == "Compare Two AWRs" and data1 and data2:
            if st.button("⬇ Download RCA Report", use_container_width=True):
                health1 = calculate_health_score(data1)
                health2 = calculate_health_score(data2)
                comp_dict = compare_periods(data1, data2).model_dump()
                rca1 = run_rca(data1)
                rca2 = run_rca(data2)
                html_str = _build_download_html(
                    data1, data2, lbl1, lbl2, health1, health2, comp_dict, rca1, rca2
                )
                fname = f"AWR-RCA-{lbl1}_vs_{lbl2}_{datetime.now().strftime('%Y%m%d')}.html"
                st.download_button(
                    "Save Report HTML",
                    data=html_str,
                    file_name=fname,
                    mime="text/html",
                    use_container_width=True,
                )

        # Logout
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        user = st.session_state.get("username", "User")
        st.markdown(
            f"<div style='font-size:11px;color:#475569;margin-bottom:6px'>Signed in as <b>{user}</b></div>",
            unsafe_allow_html=True,
        )
        if st.button("Sign Out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.markdown(
            "<div style='font-size:10px;color:#334155;margin-top:12px'>OraVision AWR Pro v3.0</div>",
            unsafe_allow_html=True,
        )

    return mode, data1, data2, lbl1, lbl2


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not login_gate():
        st.stop()

    mode, data1, data2, lbl1, lbl2 = render_sidebar()

    # ── No data yet ───────────────────────────────────────────────────────
    if data1 is None and data2 is None:
        st.markdown(
            """
            <div style="text-align:center;padding:80px 40px">
                <div style="font-size:3rem;font-weight:900;background:linear-gradient(135deg,#fff,#06b6d4 60%,#8b5cf6);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                    Oracle AWR Root Cause Analysis
                </div>
                <p style="color:#64748b;font-size:1rem;margin-top:12px">
                    Upload an AWR HTML report using the sidebar to begin analysis.
                </p>
                <div style="display:flex;justify-content:center;gap:32px;margin-top:40px;flex-wrap:wrap">
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:12px;padding:20px 24px;min-width:180px">
                        <div style="font-size:1.4rem;margin-bottom:8px">🔍</div>
                        <div style="font-size:13px;font-weight:700;color:#e2e8f0">Single AWR</div>
                        <div style="font-size:11px;color:#64748b;margin-top:4px">Full RCA, health score,<br>wait events, SQL ranking</div>
                    </div>
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:12px;padding:20px 24px;min-width:180px">
                        <div style="font-size:1.4rem;margin-bottom:8px">⚖</div>
                        <div style="font-size:13px;font-weight:700;color:#e2e8f0">Compare Two AWRs</div>
                        <div style="font-size:11px;color:#64748b;margin-top:4px">Baseline vs problem<br>delta analysis, SQL regression</div>
                    </div>
                    <div style="background:#111827;border:1px solid #1e293b;border-radius:12px;padding:20px 24px;min-width:180px">
                        <div style="font-size:1.4rem;margin-bottom:8px">📄</div>
                        <div style="font-size:13px;font-weight:700;color:#e2e8f0">Download Report</div>
                        <div style="font-size:11px;color:#64748b;margin-top:4px">Customer-ready HTML<br>report with all findings</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Single AWR ────────────────────────────────────────────────────────
    if mode == "Single AWR Report" and data1 is not None:
        render_single_awr(data1, lbl1)

    # ── Comparison ────────────────────────────────────────────────────────
    elif mode == "Compare Two AWRs":
        if data1 is not None and data2 is not None:
            render_comparison(data1, data2, lbl1, lbl2)
        elif data1 is not None:
            st.info("Baseline uploaded. Upload the Problem AWR to run comparison.")
            render_single_awr(data1, lbl1)
        else:
            st.info("Upload both AWR files to begin comparison.")


if __name__ == "__main__":
    main()
