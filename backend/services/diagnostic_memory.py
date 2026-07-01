"""
Diagnostic Memory — a deterministic, self-learning case-based reasoning (CBR) layer.

This is the silent backend "intelligence agent". It does NOT use an LLM and never
fabricates. For every AWR comparison the tool processes, it:

  1. Reduces the verdict to a compact numeric SIGNATURE (bottleneck class, severity,
     DB-Time regression bucket, AAS saturation, top wait-event fingerprint).
  2. Stores the case in a persistent library (JSON on disk).
  3. Matches each NEW comparison against the library (past cases + curated GOLDEN cases)
     using deterministic nearest-neighbour distance.
  4. Computes a CONSENSUS root cause from the most-similar confirmed cases and compares
     it to the live verdict. Agreement => confidence boost. Disagreement => silent
     drift/self-audit flag ("N similar confirmed cases pointed elsewhere").
  5. Accepts ground-truth feedback (confirm_case) so the library gets smarter over time.

Everything is reproducible: same inputs -> same signature -> same match. No magic.
"""
from __future__ import annotations
import json, os, hashlib, tempfile, time
from typing import Any

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_STORE_PATH = os.path.join(_DATA_DIR, "diagnostic_memory.json")

# DB-Time regression buckets (lower bound %, label)
_DBT_BUCKETS = [(-1e9, "improved"), (5, "flat"), (25, "minor"), (50, "moderate"),
                (100, "major"), (300, "severe"), (1e9, "extreme")]

# Feature weights for distance (higher = more discriminative)
_W_BOTTLENECK = 0.40
_W_SEVERITY   = 0.20
_W_DBT_BUCKET = 0.15
_W_AAS        = 0.10
_W_WAITS      = 0.15


# ── Signature extraction ──────────────────────────────────────────────────────

def _dbt_bucket(delta_pct: float) -> str:
    for lo, label in _DBT_BUCKETS:
        if delta_pct < lo:
            return label
    return "extreme"


def _top_wait_names(report: dict, k: int = 4) -> list[str]:
    waits = (report.get("top_wait_events") or {}).get("comparisons") or []
    ranked = sorted(waits, key=lambda x: x.get("bad_pct_db_time", 0), reverse=True)
    return [str(w.get("event_name", "")).lower().strip() for w in ranked[:k] if w.get("event_name")]


def build_signature(report: dict) -> dict[str, Any]:
    """Deterministically reduce a ComparisonReport dict to a match signature."""
    summ = report.get("summary") or {}
    dbt = float(summ.get("db_time_delta_pct", 0) or 0)
    aas_bad = float(summ.get("aas_bad", 0) or 0)
    cpu_cap = float(summ.get("cpu_capacity_used_pct", 0) or 0)
    sig = {
        "bottleneck": str(summ.get("bad_bottleneck", "Unknown")),
        "severity": str(summ.get("severity", "unknown")),
        "shift": str(summ.get("bottleneck_shift", "")),
        "dbt_bucket": _dbt_bucket(dbt),
        "dbt_pct": round(dbt, 1),
        "aas_bad": round(aas_bad, 2),
        "cpu_capacity_pct": round(cpu_cap, 1),
        "saturated": cpu_cap >= 90.0,
        "top_waits": _top_wait_names(report),
    }
    sig["hash"] = hashlib.sha1(
        json.dumps([sig["bottleneck"], sig["severity"], sig["dbt_bucket"],
                    sig["saturated"], sig["top_waits"]], sort_keys=True).encode()
    ).hexdigest()[:16]
    return sig


# ── Distance / similarity ─────────────────────────────────────────────────────

def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def _bucket_dist(a: str, b: str) -> float:
    order = [lbl for _, lbl in _DBT_BUCKETS]
    try:
        return abs(order.index(a) - order.index(b)) / (len(order) - 1)
    except ValueError:
        return 1.0


def similarity(sig_a: dict, sig_b: dict) -> float:
    """Return 0.0–1.0 similarity. Deterministic, weighted feature blend."""
    s = 0.0
    s += _W_BOTTLENECK * (1.0 if sig_a["bottleneck"] == sig_b["bottleneck"] else 0.0)
    s += _W_SEVERITY   * (1.0 if sig_a["severity"] == sig_b["severity"] else 0.0)
    s += _W_DBT_BUCKET * (1.0 - _bucket_dist(sig_a["dbt_bucket"], sig_b["dbt_bucket"]))
    s += _W_AAS        * (1.0 if sig_a.get("saturated") == sig_b.get("saturated") else 0.0)
    s += _W_WAITS      * _jaccard(sig_a.get("top_waits", []), sig_b.get("top_waits", []))
    return round(s, 4)


# ── Persistent case store ─────────────────────────────────────────────────────

class CaseStore:
    def __init__(self, path: str = _STORE_PATH):
        self.path = path
        self.cases: list[dict] = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.cases = json.load(f).get("cases", [])
            except (json.JSONDecodeError, OSError):
                self.cases = []
        if not self.cases:
            self.cases = list(_GOLDEN_CASES)
            self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"cases": self.cases, "updated": time.time()}, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            if os.path.exists(tmp):
                os.remove(tmp)

    def add(self, case: dict) -> None:
        # Dedup by signature hash — bump seen count instead of duplicating
        for c in self.cases:
            if c["signature"]["hash"] == case["signature"]["hash"] and c.get("source") != "golden":
                c["seen"] = c.get("seen", 1) + 1
                c["last_seen"] = case.get("last_seen")
                self._save()
                return
        self.cases.append(case)
        self._save()

    def confirm(self, case_id: str, confirmed_root_cause: str) -> bool:
        for c in self.cases:
            if c.get("id") == case_id:
                c["confirmed_root_cause"] = confirmed_root_cause
                c["confirmed"] = True
                self._save()
                return True
        return False


# ── Public engine ─────────────────────────────────────────────────────────────

_store: CaseStore | None = None

def _get_store() -> CaseStore:
    global _store
    if _store is None:
        _store = CaseStore()
    return _store


def record_case(report: dict, db_name: str = "", label: str | None = None,
                novel: bool = False) -> dict:
    """Store the current comparison as a case. Returns the stored record.
    Failure-proof: never raises into the request path.
    """
    try:
        sig = build_signature(report)
    except Exception:
        return {"id": "", "error": "could not build signature"}
    case = {
        "id": f"{sig['hash']}-{int(time.time()*1000)%100000}",
        "db_name": db_name or (report.get("summary") or {}).get("good_period", ""),
        "signature": sig,
        "verdict_bottleneck": sig["bottleneck"],
        "verdict_severity": sig["severity"],
        "confirmed": False,
        "confirmed_root_cause": label or "",
        "source": "live",
        "novel": bool(novel),
        "seen": 1,
        "last_seen": time.time(),
    }
    try:
        _get_store().add(case)
    except Exception:
        return {"id": case["id"], "error": "could not persist"}
    return case


def stats() -> dict:
    """Library coverage stats — what the dashboard knows vs. what is new/unconfirmed."""
    try:
        cases = _get_store().cases
    except Exception:
        return {"library_size": 0}
    by_class: dict[str, int] = {}
    confirmed = golden = live = novel = 0
    for c in cases:
        b = c.get("signature", {}).get("bottleneck", "Unknown")
        by_class[b] = by_class.get(b, 0) + 1
        if c.get("confirmed"):
            confirmed += 1
        if c.get("source") == "golden":
            golden += 1
        if c.get("source") == "live":
            live += 1
        if c.get("novel"):
            novel += 1
    return {
        "library_size": len(cases),
        "golden_cases": golden,
        "learned_cases": live,
        "confirmed_cases": confirmed,
        "novel_unrecognized": novel,
        "coverage_by_bottleneck": dict(sorted(by_class.items(), key=lambda x: -x[1])),
        "known_bottleneck_classes": sorted(by_class.keys()),
    }


def all_cases(limit: int = 200) -> list[dict]:
    """Return stored cases (most recent first) for inspection/audit."""
    try:
        cases = list(_get_store().cases)
    except Exception:
        return []
    cases.sort(key=lambda c: (c.get("last_seen") or 0), reverse=True)
    return cases[:limit]


def match(report: dict, k: int = 5, min_sim: float = 0.55) -> dict:
    """Match the live comparison against the library. Backend-only intelligence.

    Returns consensus, agreement, a confidence adjustment, a silent drift flag,
    and a NOVELTY verdict (whether this pattern has ever been seen before).
    Failure-proof: any malformed input yields a safe, empty intelligence block.
    """
    try:
        store = _get_store()
        live = build_signature(report)
    except Exception:
        return {
            "matched": 0, "library_size": 0, "consensus_root_cause": "",
            "consensus_agreement": 0.0, "aligns_with_history": False,
            "confidence_delta": 0.0, "drift_warning": "", "is_novel": False,
            "novelty_reason": "", "neighbours": [], "signature": {},
            "error": "intelligence unavailable",
        }
    scored = []
    best_any = 0.0
    for c in store.cases:
        try:
            sim = similarity(live, c["signature"])
        except Exception:
            continue
        best_any = max(best_any, sim)
        if sim >= min_sim:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    neighbours = scored[:k]

    # ── Novelty: has the dashboard ever seen anything like this? ──────────────
    is_novel = len(neighbours) == 0
    novelty_reason = ""
    if is_novel:
        novelty_reason = (
            f"NOVEL pattern — closest known case is only {best_any:.0%} similar "
            f"(below {min_sim:.0%} recognition threshold). Bottleneck '{live['bottleneck']}' "
            f"with this wait fingerprint has not been seen before; recording for future learning."
        )

    # Consensus from CONFIRMED neighbours (ground truth) — fall back to all neighbours
    confirmed = [(s, c) for s, c in neighbours if c.get("confirmed")]
    pool = confirmed or neighbours

    votes: dict[str, float] = {}
    for sim, c in pool:
        key = c.get("confirmed_root_cause") or c["signature"]["bottleneck"]
        votes[key] = votes.get(key, 0.0) + sim
    consensus, consensus_weight = ("", 0.0)
    if votes:
        consensus, consensus_weight = max(votes.items(), key=lambda x: x[1])

    total_w = sum(votes.values()) or 1.0
    agreement = round(consensus_weight / total_w, 3)

    live_label = live["bottleneck"]
    aligns = bool(consensus) and (
        consensus == live_label or live_label.lower() in consensus.lower()
    )

    # Confidence adjustment + silent self-audit flag
    drift = ""
    confidence_delta = 0.0
    if neighbours:
        if aligns and agreement >= 0.6:
            confidence_delta = round(min(0.15, 0.05 + 0.1 * agreement), 3)
        elif consensus and not aligns and len(confirmed) >= 2 and agreement >= 0.6:
            confidence_delta = -round(min(0.20, 0.1 + 0.1 * agreement), 3)
            drift = (
                f"Self-audit: live verdict '{live_label}' disagrees with {len(confirmed)} "
                f"similar CONFIRMED case(s) whose consensus was '{consensus}' "
                f"(agreement {agreement:.0%}). Recommend cross-checking with ASH/ADDM before acting."
            )

    return {
        "matched": len(neighbours),
        "library_size": len(store.cases),
        "consensus_root_cause": consensus,
        "consensus_agreement": agreement,
        "aligns_with_history": aligns,
        "confidence_delta": confidence_delta,
        "drift_warning": drift,
        "is_novel": is_novel,
        "novelty_reason": novelty_reason,
        "closest_similarity": round(best_any, 4),
        "neighbours": [
            {
                "id": c.get("id"),
                "similarity": sim,
                "bottleneck": c["signature"]["bottleneck"],
                "severity": c["signature"]["severity"],
                "confirmed": c.get("confirmed", False),
                "confirmed_root_cause": c.get("confirmed_root_cause", ""),
                "source": c.get("source", "live"),
                "db_name": c.get("db_name", ""),
            }
            for sim, c in neighbours
        ],
        "signature": live,
    }


def confirm_case(case_id: str, confirmed_root_cause: str) -> bool:
    """Feedback loop: tag a stored case with its DB-validated root cause."""
    return _get_store().confirm(case_id, confirmed_root_cause)


# ── Golden seed library (canonical, ground-truth labelled) ────────────────────
# Seeds a fresh install so matching is meaningful from day one. Mirrors the
# benchmark taxonomy. These are 'confirmed' by construction.

def _golden(bottleneck, severity, dbt_bucket, saturated, waits, root_cause):
    sig = {
        "bottleneck": bottleneck, "severity": severity, "shift": "",
        "dbt_bucket": dbt_bucket, "dbt_pct": 0.0, "aas_bad": 0.0,
        "cpu_capacity_pct": 95.0 if saturated else 40.0, "saturated": saturated,
        "top_waits": waits,
    }
    sig["hash"] = hashlib.sha1(
        json.dumps([bottleneck, severity, dbt_bucket, saturated, waits], sort_keys=True).encode()
    ).hexdigest()[:16]
    return {
        "id": f"gold-{sig['hash']}", "db_name": "GOLDEN", "signature": sig,
        "verdict_bottleneck": bottleneck, "verdict_severity": severity,
        "confirmed": True, "confirmed_root_cause": root_cause, "source": "golden",
        "seen": 1, "last_seen": None,
    }


_GOLDEN_CASES: list[dict] = [
    _golden("CPU", "critical", "major", True, ["cpu"], "CPU"),
    _golden("I/O", "critical", "major", False, ["db file sequential read"], "I/O"),
    _golden("I/O", "critical", "major", False, ["db file scattered read"], "I/O"),
    _golden("Commit", "critical", "major", False, ["log file sync"], "Commit"),
    _golden("Cluster", "critical", "major", False, ["gc buffer busy acquire"], "Cluster"),
    _golden("Cluster", "critical", "major", False, ["gc cr block busy"], "Cluster"),
    _golden("Concurrency", "critical", "major", False, ["buffer busy waits"], "Concurrency"),
    _golden("Concurrency", "critical", "major", False, ["library cache lock"], "Concurrency"),
    _golden("Concurrency", "critical", "major", False, ["latch: shared pool"], "Concurrency"),
    _golden("Concurrency", "critical", "major", False, ["enq: tx - row lock contention"], "Concurrency"),
    _golden("Network", "critical", "major", False, ["sql*net more data to client"], "Network"),
    _golden("Concurrency", "critical", "major", False, ["resmgr:cpu quantum"], "Resource Manager throttling"),
]
