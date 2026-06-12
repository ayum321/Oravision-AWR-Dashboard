"""Probe raw AWR HTML: which segment tables exist and what does the parser's lookup return for each?"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from bs4 import BeautifulSoup

PATH = r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRGD5GV4 Snap 122665 thru 122669.html"
html = open(PATH, encoding="utf-8", errors="replace").read()
soup = BeautifulSoup(html, "lxml")

def _clean(s): return re.sub(r"\s+", " ", s or "").strip()

# 1. list all table summary attributes containing 'segments'
print("=== table summary attrs containing 'segment' ===")
for t in soup.find_all("table"):
    s = (t.get("summary") or "").lower()
    if "segment" in s:
        print(" ", s[:120])

# 2. emulate parser lookups
def find_by_summary(kw):
    for t in soup.find_all("table"):
        if kw in (t.get("summary") or "").lower():
            return t
    return None

def find_after_heading(txt):
    pattern = re.compile(re.escape(txt), re.IGNORECASE)
    for tag in soup.find_all(["h2","h3","h4","a","b","th"]):
        if pattern.search(_clean(tag.get_text())):
            sib = tag
            for _ in range(30):
                sib = sib.find_next()
                if sib is None: break
                if sib.name == "table":
                    return sib, _clean(tag.get_text()), tag.name
    return None

segment_tables = ["logical reads","physical reads","physical read requests","direct physical reads",
    "unoptimized reads","optimized reads","physical writes","physical write requests",
    "direct physical writes","buffer gets","table scans","db blocks changes","db block changes",
    "row lock waits","itl waits","buffer busy waits"]

print("\n=== parser lookup emulation ===")
for kw in segment_tables:
    t = find_by_summary(f"segments by {kw}")
    if t is not None:
        print(f"  {kw:26s} -> SUMMARY match: {(t.get('summary') or '')[:80]}")
        continue
    r = find_after_heading(f"Segments by {kw.title()}")
    if r:
        t, anchortxt, tagname = r
        hdr = [_clean(td.get_text()) for td in t.find_all("tr")[0].find_all(["td","th"])][:6]
        print(f"  {kw:26s} -> HEADING fallback via <{tagname}> '{anchortxt[:40]}' -> table hdr: {hdr}")
    else:
        r2 = find_after_heading(f"Segments by {kw.upper()}")
        if r2:
            t, anchortxt, tagname = r2
            hdr = [_clean(td.get_text()) for td in t.find_all("tr")[0].find_all(["td","th"])][:6]
            print(f"  {kw:26s} -> UPPER fallback via <{tagname}> '{anchortxt[:40]}' -> table hdr: {hdr}")
        else:
            print(f"  {kw:26s} -> NOT FOUND (section absent)")
