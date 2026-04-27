#!/usr/bin/env python3
"""Analyze results.csv produced by load.py.

Reports per phase: status mix, latency percentiles, Caddy cache Age-header
breakdown, and per-URL latency in the REPEAT phase.

Usage:
  python analyze.py [results.csv]
"""
import csv
import sys
from collections import Counter, defaultdict
from statistics import median

def pct(xs, p):
    if not xs:
        return 0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return s[k]

def main(path):
    rows = list(csv.DictReader(open(path)))
    print(f"Total rows: {len(rows)}")

    for phase in ["A_REPEAT", "B_UNIQUE"]:
        sub = [r for r in rows if r["phase"] == phase]
        if not sub:
            continue
        print(f"\n=== {phase} ({len(sub)} reqs) ===")
        statuses = Counter(r["status"] for r in sub)
        print(f"  status mix: {dict(statuses)}")
        errs = [r for r in sub if r["err"]]
        if errs:
            print(f"  errors: {len(errs)}, sample: {errs[0]['err']}")
        ok = [r for r in sub if r["status"] == "200"]
        lat = [float(r["ms"]) for r in ok]
        if lat:
            print(f"  latency ms (n={len(lat)}): "
                  f"min={min(lat):.0f} p50={median(lat):.0f} "
                  f"p90={pct(lat,90):.0f} p99={pct(lat,99):.0f} max={max(lat):.0f}")
        ages = [int(r["age"]) for r in ok if r["age"].isdigit()]
        no_age = sum(1 for r in ok if not r["age"])
        age0 = sum(1 for a in ages if a == 0)
        age_pos = sum(1 for a in ages if a > 0)
        print(f"  upstream cache: age>0 (HIT)={age_pos}  age=0 (FRESH)={age0}  "
              f"no-age header={no_age}")
        if ages:
            print(f"  age values (sec): min={min(ages)} med={median(ages):.0f} max={max(ages)}")

    print("\n=== A_REPEAT: per-URL latency ===")
    by_url_seq = defaultdict(list)
    for r in rows:
        if r["phase"] != "A_REPEAT" or r["status"] != "200":
            continue
        by_url_seq[r["path"]].append(float(r["ms"]))
    for path, lats in by_url_seq.items():
        if not lats:
            continue
        print(f"  {path:40s}  n={len(lats):3d}  "
              f"min={min(lats):5.0f}  p50={median(lats):5.0f}  "
              f"p90={pct(lats,90):5.0f}  max={max(lats):5.0f}")

    print("\n=== B_UNIQUE: latency by URL shape ===")
    shapes = defaultdict(list)
    for r in rows:
        if r["phase"] != "B_UNIQUE" or r["status"] != "200":
            continue
        p = r["path"]
        if "/record/" in p:
            shape = "record"
        elif "/browser/?page=" in p:
            shape = "browser_page"
        elif p.count("/") >= 4 and "?page=" in p:
            shape = "state_page"
        else:
            shape = "other"
        shapes[shape].append(float(r["ms"]))
    for s, lats in shapes.items():
        print(f"  {s:15s}  n={len(lats):3d}  "
              f"min={min(lats):5.0f}  p50={median(lats):5.0f}  "
              f"p90={pct(lats,90):5.0f}  max={max(lats):5.0f}")

    print("\n=== Cache-Control header mix (200s only) ===")
    cc = Counter(r["cache_control"] for r in rows if r["status"] == "200")
    for v, n in cc.most_common():
        print(f"  {n:4d}  {v!r}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.csv")
