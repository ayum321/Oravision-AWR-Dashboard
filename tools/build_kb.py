"""
build_kb.py  —  Step 3 of the Outlook -> KB pipeline.

Reads the .json files the Outlook macro dropped in  outlook_drop  and turns
them into a clean, de-duplicated knowledge base:

    outlook_drop\\*.json   ->   knowledge_base.jsonl     (one record per line)
                           ->   kb_markdown\\<id>.md      (human-readable copy)

It is idempotent: re-running after exporting more e-mails merges new messages
and never doubles up (records are keyed by a stable content hash).

Run from the workspace root:
    python tools/build_kb.py
"""
from __future__ import annotations

import email
import hashlib
import json
import re
import sys
from datetime import datetime
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DROP = ROOT / "outlook_drop"
JSONL = ROOT / "knowledge_base.jsonl"
MD_DIR = ROOT / "kb_markdown"

# First-name -> display name. Only mail from these people is kept.
ENGINEERS = {
    "rangadu": "Rangadu",
    "zafar": "Zafar",
    "sukhamoy": "Sukhamoy",
    "virendra": "Virendra",
    "ayush": "Ayush",
}


def _match_engineer(from_name: str, from_email: str) -> str | None:
    hay = f"{from_name} {from_email}".lower()
    for key, disp in ENGINEERS.items():
        if re.search(rf"\b{re.escape(key)}\b", hay) or key in hay:
            return disp
    return None


def _rec_id(from_email: str, subject: str, received: str) -> str:
    raw = f"{from_email.strip().lower()}|{subject.strip().lower()}|{received.strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _load_existing() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("id"):
                    out[rec["id"]] = rec
            except json.JSONDecodeError:
                continue
    return out


def _fields_from_json(fp: Path) -> tuple[str, str, str, str, str]:
    obj = json.loads(fp.read_text(encoding="utf-8-sig", errors="replace"))
    return (
        str(obj.get("from_name", "")).strip(),
        str(obj.get("from_email", "")).strip(),
        str(obj.get("subject", "")).strip(),
        str(obj.get("received", "")).strip(),
        str(obj.get("body", "")),
    )


def _eml_body(msg) -> str:
    """Prefer the plain-text part; fall back to stripped HTML."""
    try:
        part = msg.get_body(preferencelist=("plain",))
        if part is not None:
            return part.get_content()
    except Exception:  # noqa: BLE001
        pass
    try:
        part = msg.get_body(preferencelist=("html",))
        if part is not None:
            html = part.get_content()
            html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
            text = re.sub(r"(?s)<[^>]+>", " ", html)
            return re.sub(r"[ \t]+", " ", text)
    except Exception:  # noqa: BLE001
        pass
    return ""


def _fields_from_eml(fp: Path) -> tuple[str, str, str, str, str]:
    msg = email.message_from_bytes(fp.read_bytes(), policy=policy.default)
    name, addr = parseaddr(msg.get("From", ""))
    subject = str(msg.get("Subject", "")).strip()
    received = ""
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            received = dt.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        received = ""
    return name.strip(), addr.strip(), subject, received, _eml_body(msg)


def _read_drop() -> list[dict]:
    records: list[dict] = []
    if not DROP.exists():
        return records
    files = sorted(list(DROP.glob("*.json")) + list(DROP.glob("*.eml")))
    for fp in files:
        try:
            if fp.suffix.lower() == ".eml":
                from_name, from_email, subject, received, body = _fields_from_eml(fp)
            else:
                from_name, from_email, subject, received, body = _fields_from_json(fp)
        except Exception as e:  # noqa: BLE001 — skip an unreadable drop file
            print(f"  skip {fp.name}: {e}")
            continue
        eng = _match_engineer(from_name, from_email)
        if not eng:
            continue  # not one of the tracked engineers
        rid = _rec_id(from_email or from_name, subject, received)
        records.append({
            "id": rid,
            "engineer": eng,
            "from_name": from_name,
            "from_email": from_email,
            "subject": subject,
            "received": received,
            "body": body,
            "source_file": fp.name,
        })
    return records


def _write_markdown(rec: dict) -> None:
    MD_DIR.mkdir(parents=True, exist_ok=True)
    fp = MD_DIR / f"{rec['id']}.md"
    fp.write_text(
        f"# {rec['subject'] or '(no subject)'}\n\n"
        f"- **Engineer:** {rec['engineer']}\n"
        f"- **From:** {rec['from_name']} <{rec['from_email']}>\n"
        f"- **Received:** {rec['received']}\n"
        f"- **ID:** {rec['id']}\n\n"
        f"---\n\n{rec['body']}\n",
        encoding="utf-8",
    )


def _sort_key(rec: dict) -> str:
    return rec.get("received", "") or ""


def main() -> int:
    existing = _load_existing()
    before = len(existing)

    added = 0
    for rec in _read_drop():
        if rec["id"] not in existing:
            added += 1
        existing[rec["id"]] = rec  # newest export wins for the same id

    merged = sorted(existing.values(), key=_sort_key)

    JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + ("\n" if merged else ""),
        encoding="utf-8",
    )
    for rec in merged:
        _write_markdown(rec)

    by_eng: dict[str, int] = {}
    for r in merged:
        by_eng[r["engineer"]] = by_eng.get(r["engineer"], 0) + 1

    print(f"knowledge_base.jsonl: {len(merged)} records "
          f"({added} new, {before} already present)")
    print(f"kb_markdown\\: {len(merged)} files")
    if by_eng:
        print("By engineer: " + ", ".join(f"{k}={v}" for k, v in sorted(by_eng.items())))
    else:
        print(f"No matching e-mails found. Export some into {DROP} and re-run.")
    print(f"Generated {datetime.now():%Y-%m-%d %H:%M}. Next: python tools/build_digest.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
