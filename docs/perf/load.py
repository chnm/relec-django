#!/usr/bin/env python3
"""Aggressive blackbox load test against the census browser.

Two phases, both at concurrency=20, no inter-request delay:
  A. REPEAT  -- 500 reqs across 5 URLs (cache should absorb)
  B. UNIQUE  -- 500 reqs across 500 distinct URLs (cache miss -> daphne/DB)

Per-request log: phase, url, status, ms, bytes, age, cache-control.

Configure via env:
  RELEC_HOST  -- target base URL (default http://localhost:8000)
  RELEC_OUT   -- output CSV path (default ./results.csv)
"""
import csv
import os
import random
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

HOST = os.environ.get("RELEC_HOST", "http://localhost:8000").rstrip("/")
OUT = os.environ.get("RELEC_OUT", "./results.csv")
UA = "claude-code-scrape-sim/1.0 (authorized owner load test)"
TIMEOUT = 20
WORKERS = 20

US_STATES = ["AL","AZ","AR","CA","CO","CT","DE","FL","GA","ID","IL","IN","IA",
             "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
             "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD",
             "TN","TX","UT","VT","VA","WA","WV","WI","WY"]

REPEAT_URLS = [
    "/census/browser/",
    "/census/browser/VA/",
    "/census/browser/CA/",
    "/census/browser/?page=2",
    "/census/record/6875/",
]

random.seed(42)

def build_unique(n=500):
    urls = set()
    while len(urls) < n:
        r = random.random()
        if r < 0.40:
            urls.add(f"/census/browser/?page={random.randint(1, 11380)}")
        elif r < 0.70:
            st = random.choice(US_STATES)
            urls.add(f"/census/browser/{st}/?page={random.randint(1, 50)}")
        else:
            urls.add(f"/census/record/{random.randint(6875, 25000)}/")
    return list(urls)

def fetch(phase, path):
    url = HOST + path
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    status = None
    age = ""
    cc = ""
    nbytes = 0
    err = ""
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            status = resp.status
            age = resp.headers.get("age", "")
            cc = resp.headers.get("cache-control", "")
            data = resp.read()
            nbytes = len(data)
    except urllib.error.HTTPError as e:
        status = e.code
        age = e.headers.get("age", "") if e.headers else ""
        cc = e.headers.get("cache-control", "") if e.headers else ""
    except Exception as e:
        err = type(e).__name__ + ":" + str(e)[:80]
    ms = (time.perf_counter() - t0) * 1000
    return (phase, path, status, round(ms, 1), nbytes, age, cc, err)

def run_phase(name, plan, log):
    print(f"\n=== Phase {name}: {len(plan)} requests, {WORKERS} workers ===", flush=True)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(fetch, name, p) for p in plan]
        done = 0
        for f in as_completed(futures):
            row = f.result()
            log.writerow(row)
            done += 1
            if done % 100 == 0:
                print(f"  {name}: {done}/{len(plan)} done", flush=True)
    elapsed = time.perf_counter() - t0
    print(f"  {name} elapsed: {elapsed:.1f}s  rate: {len(plan)/elapsed:.1f} rps", flush=True)

def main():
    print(f"target: {HOST}\noutput: {OUT}", flush=True)
    out = open(OUT, "w", newline="")
    log = csv.writer(out)
    log.writerow(["phase","path","status","ms","bytes","age","cache_control","err"])

    plan_a = REPEAT_URLS * 100
    random.shuffle(plan_a)
    run_phase("A_REPEAT", plan_a, log)

    plan_b = build_unique(500)
    random.shuffle(plan_b)
    run_phase("B_UNIQUE", plan_b, log)

    out.close()
    print(f"\nWrote {OUT}", flush=True)

if __name__ == "__main__":
    main()
