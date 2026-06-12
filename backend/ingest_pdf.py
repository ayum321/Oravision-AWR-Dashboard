#!/usr/bin/env python
"""
ingest_pdf.py — One-time PDF ingestion script for the AWR Dashboard
====================================================================
Reads an Oracle documentation PDF and stores searchable chunks in the
shared rag_kb.db SQLite knowledge base.

Usage
-----
    cd backend
    python ingest_pdf.py "C:\\path\\to\\sql-tuning-guide.pdf"

    # Force re-ingest (clears previous chunks for that file):
    python ingest_pdf.py "C:\\path\\to\\sql-tuning-guide.pdf" --replace

    # Check what's stored:
    python ingest_pdf.py --status

    # Query the stored knowledge (for testing):
    python ingest_pdf.py --query "log file sync redo buffer"

Requirements
------------
    pip install pdfplumber
    (run from the backend/ directory so services/ is importable)
"""
from __future__ import annotations

import argparse
import sys
import os

# ensure backend/ is on PYTHONPATH when run directly
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from services import pdf_kb


def _cmd_ingest(pdf_path: str, replace: bool) -> None:
    print(f"\nIngesting: {pdf_path}")
    print(f"Replace existing: {replace}\n")
    try:
        n = pdf_kb.ingest_pdf(pdf_path, replace_existing=replace)
        print(f"✔  Stored {n} knowledge chunks.")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # show status after ingestion
    _cmd_status()


def _cmd_status() -> None:
    status = pdf_kb.kb_status()
    print(f"\nKnowledge base — {status['total_chunks']} total chunks\n")
    if not status["sources"]:
        print("  (empty — no PDFs ingested yet)")
        return
    for src in status["sources"]:
        import datetime
        ts = datetime.datetime.fromtimestamp(src["last_ingested"]).strftime("%Y-%m-%d %H:%M")
        print(f"  {src['source_file']:50s}  {src['chunks']:4d} chunks  (ingested {ts})")


def _cmd_query(query: str, top_k: int) -> None:
    keywords = [k.strip() for k in query.split() if len(k.strip()) > 2]
    print(f"\nQuerying for: {keywords}\n")
    results = pdf_kb.query_kb(keywords, top_k=top_k)
    if not results:
        print("  No results found. Is the PDF ingested? Run --status to check.")
        return
    for i, r in enumerate(results, start=1):
        print(f"[{i}] {r['source_file']} — p.{r['page_num']}  section: {r['section']}")
        print(f"     score: {r['score']:.3f}   keywords: {', '.join(r['keywords'][:5])}")
        print(f"     {r['chunk_text'][:300]}…" if len(r['chunk_text']) > 300 else f"     {r['chunk_text']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Oracle PDF documentation into the AWR Dashboard knowledge base."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("pdf_path", nargs="?", help="Path to the PDF file to ingest.")
    group.add_argument("--status", action="store_true", help="Show knowledge base status.")
    group.add_argument("--query", metavar="TEXT", help="Test query against stored chunks.")
    parser.add_argument("--replace", action="store_true", default=True,
                        help="Replace existing chunks for this PDF (default: True).")
    parser.add_argument("--top-k", type=int, default=5, metavar="N",
                        help="Number of results to show for --query (default: 5).")

    args = parser.parse_args()

    if args.status:
        _cmd_status()
    elif args.query:
        _cmd_query(args.query, args.top_k)
    elif args.pdf_path:
        _cmd_ingest(args.pdf_path, args.replace)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
