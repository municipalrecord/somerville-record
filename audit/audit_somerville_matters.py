#!/usr/bin/env python3
"""Somerville accuracy audit: verify a random sample of matters against the
city's live Legistar API (same methodology as Cambridge's
audit_agenda_items.py; same publish-the-seed reproducibility).

    python3 audit_somerville_matters.py [--n 1000] [--seed 20260712]

For each sampled matter, fetch the API's CURRENT record and compare what
we display: file number, title, type, status, intro date. Writes
Data/audit_somerville_matters.csv (resumable) + prints a summary.
"""
import argparse
import csv
import json
import random
import re
import time
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "Somerville"
OUT_CSV = Path(__file__).resolve().parent.parent / "audit_somerville_matters.csv"
SITE_OUT = Path(__file__).resolve().parent.parent.parent / "site" / "out-somerville"
BASE = "https://webapi.legistar.com/v1/somervillema"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
DELAY = 0.35

FIELDS = ["matter_id", "file_no", "portal_http", "file_match", "title_match",
          "type_match", "status_match", "intro_match", "site_page", "note"]


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def fetch(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            r = urllib.request.urlopen(req, timeout=30)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
        except Exception:
            if attempt == tries - 1:
                return 0, b""
            time.sleep(3)


def cmp_field(ours, theirs):
    a, b = norm(str(ours or "")), norm(str(theirs or ""))
    if a == b:
        return "exact"
    if a.casefold() == b.casefold():
        return "case"
    if a and b and (a.startswith(b) or b.startswith(a)):
        return "prefix"
    return "MISMATCH"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260712)
    args = ap.parse_args()

    matters = json.loads((SRC / "matters.json").read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    sample = rng.sample(matters, min(args.n, len(matters)))

    done = {}
    if OUT_CSV.exists():
        with open(OUT_CSV, encoding="utf-8") as f:
            done = {r["matter_id"]: r for r in csv.DictReader(f)}
    out = open(OUT_CSV, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(out, fieldnames=FIELDS)
    if not done:
        w.writeheader()

    checked = 0
    for m in sample:
        mid = str(m["MatterId"])
        if mid in done:
            continue
        row = {"matter_id": mid, "file_no": m.get("MatterFile") or "",
               "note": ""}
        status, data = fetch(f"{BASE}/matters/{mid}")
        row["portal_http"] = status
        if status == 200 and data:
            cur = json.loads(data)
            row["file_match"] = cmp_field(m.get("MatterFile"),
                                          cur.get("MatterFile"))
            row["title_match"] = cmp_field(m.get("MatterTitle"),
                                           cur.get("MatterTitle"))
            row["type_match"] = cmp_field(m.get("MatterTypeName"),
                                          cur.get("MatterTypeName"))
            row["status_match"] = cmp_field(m.get("MatterStatusName"),
                                            cur.get("MatterStatusName"))
            row["intro_match"] = cmp_field((m.get("MatterIntroDate") or "")[:10],
                                           (cur.get("MatterIntroDate") or "")[:10])
            keys = {"file": "MatterFile", "title": "MatterTitle",
                    "type": "MatterTypeName", "status": "MatterStatusName"}
            for f_, k in keys.items():
                if row[f_ + "_match"] == "MISMATCH":
                    ours = norm(str(m.get(k) or ""))
                    theirs = norm(str(cur.get(k) or ""))
                    row["note"] += f"{f_}: ours {ours[:60]!r} vs {theirs[:60]!r}; "
        else:
            for f_ in ("file_match", "title_match", "type_match",
                       "status_match", "intro_match"):
                row[f_] = "n/a"
            row["note"] = "api record unavailable"
        stem = slug(str(m.get("MatterFile") or m["MatterId"]))
        row["site_page"] = ("yes" if (SITE_OUT / "matters" / f"{stem}.html").exists()
                            else "none")
        w.writerow(row)
        out.flush()
        checked += 1
        if checked % 100 == 0:
            print(f"  {checked} checked", flush=True)
        time.sleep(DELAY)
    out.close()

    with open(OUT_CSV, encoding="utf-8") as f:
        allr = list(csv.DictReader(f))
    n = len(allr)
    print(f"\n=== SOMERVILLE AUDIT SUMMARY (n={n}, seed={args.seed}) ===")
    print(f"api records found: {sum(1 for r in allr if r['portal_http'] == '200')}")
    for f_ in ("file", "title", "type", "status", "intro"):
        ex = sum(1 for r in allr if r[f_ + '_match'] == 'exact')
        mm = sum(1 for r in allr if r[f_ + '_match'] == 'MISMATCH')
        print(f"{f_:7} exact: {ex}  mismatch: {mm}")
    print(f"site page present: {sum(1 for r in allr if r['site_page'] == 'yes')}")
    for r in [r for r in allr if "MISMATCH" in
              (r['title_match'], r['file_match'])][:15]:
        print(f"  !! {r['file_no']} ({r['matter_id']}): {r['note'][:140]}")


if __name__ == "__main__":
    main()
