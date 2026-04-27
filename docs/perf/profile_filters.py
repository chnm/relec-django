"""Verify each filter path of /census/browser/ stays correct + measures SQL time.

Each path is exercised cold (cache.clear() before each) so we see the
worst-case SQL cost per filter shape:

  A. unfiltered, deep page         -- the scrape path
  B. has_membership=yes            -- Exists subquery path
  C. urban_rural=urban             -- Exists subquery path
  D. state filter only             -- no DISTINCT needed
  E. search=...                    -- still uses DISTINCT (not regressed)
  F. denomination=...              -- still uses DISTINCT (not regressed)
"""
import os
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
settings.DEBUG = True

from django.core.cache import cache
from django.db import connection, reset_queries
from django.test import Client


def hit(client, label, url):
    cache.clear()
    reset_queries()
    t0 = time.perf_counter()
    r = client.get(url)
    elapsed = (time.perf_counter() - t0) * 1000
    sql_ms = sum(float(q["time"]) for q in connection.queries) * 1000
    slow = sorted(connection.queries, key=lambda q: -float(q["time"]))[:3]
    print(f"\n{label}")
    print(f"  status={r.status_code} wall={elapsed:.0f}ms sql={sql_ms:.0f}ms "
          f"queries={len(connection.queries)}")
    for q in slow:
        snippet = q["sql"][:120].replace("\n", " ")
        print(f"    {q['time']}s  {snippet}...")


def main():
    client = Client(HTTP_HOST="localhost", SERVER_NAME="localhost")
    hit(client, "A. unfiltered, deep page",
        "/census/browser/?page=11000")
    hit(client, "B. has_membership=yes (Exists path)",
        "/census/browser/?page=100&has_membership=yes")
    hit(client, "C. urban_rural=urban (Exists path)",
        "/census/browser/?page=100&urban_rural=urban")
    hit(client, "D. state filter only (no distinct needed)",
        "/census/browser/CA/?page=10")
    hit(client, "E. search filter (forces distinct)",
        "/census/browser/?page=5&search=baptist")
    hit(client, "F. denomination filter (forces distinct)",
        "/census/browser/?page=5&denomination=14")


if __name__ == "__main__":
    main()
