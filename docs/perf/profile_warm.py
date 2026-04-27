"""Verify the unfiltered-count cache is reused across requests.

Hits /census/browser/?page=11000 three times. The first run is fully cold;
subsequent runs use a query-string cachebuster so @cache_page misses but
the count cache (`census_total_unfiltered`) is hit. After the patch in
census/views.py, runs 2 and 3 should show count_queries=0.
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
    reset_queries()
    t0 = time.perf_counter()
    r = client.get(url)
    elapsed = (time.perf_counter() - t0) * 1000
    counts = [q for q in connection.queries
              if "COUNT(*)" in q["sql"].upper()]
    distincts = [q for q in connection.queries
                 if "SELECT DISTINCT" in q["sql"].upper()
                 and 'FROM "census_censusschedule"' in q["sql"]]
    sql_ms = sum(float(q["time"]) for q in connection.queries) * 1000
    print(f"{label}: status={r.status_code} wall={elapsed:.0f}ms "
          f"sql={sql_ms:.0f}ms queries={len(connection.queries)} "
          f"count_queries={len(counts)} distinct_main={len(distincts)}")


def main():
    cache.clear()
    client = Client(HTTP_HOST="localhost", SERVER_NAME="localhost")
    hit(client, "1st (all cold)", "/census/browser/?page=11000")
    hit(client, "2nd (count cache warm, page cache cold)",
        "/census/browser/?page=11000&_cb=1")
    hit(client, "3rd (count cache warm)",
        "/census/browser/?page=11000&_cb=2")


if __name__ == "__main__":
    main()
