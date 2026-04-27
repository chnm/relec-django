"""Capture SQL from the view, then EXPLAIN (ANALYZE, BUFFERS) each slow one.

Use when you need the actual Postgres plan -- shows whether a sort spills
to disk, which nodes are expensive, whether indexes are used.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
settings.DEBUG = True

from django.core.cache import cache
from django.db import connection, reset_queries
from django.test import Client


URL = os.environ.get("PROFILE_URL", "/census/browser/?page=11000")
SLOW_MS = float(os.environ.get("SLOW_MS", "100"))


def main():
    cache.clear()
    client = Client(HTTP_HOST="localhost", SERVER_NAME="localhost")
    reset_queries()
    client.get(URL)

    qs = sorted(connection.queries, key=lambda q: -float(q["time"]))
    slow_sql = [q for q in qs if float(q["time"]) * 1000 > SLOW_MS]
    print(f"Found {len(slow_sql)} queries > {SLOW_MS:.0f}ms")

    with connection.cursor() as cur:
        for i, q in enumerate(slow_sql):
            sql = q["sql"]
            print(f"\n========== QUERY #{i+1}  ({q['time']}s in Django) ==========")
            print(f"SQL length: {len(sql)} chars")
            print(f"SQL tail (last 400 chars):\n...{sql[-400:]}\n")
            print("--- EXPLAIN ANALYZE ---")
            try:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql)
                for row in cur.fetchall():
                    print(row[0])
            except Exception as e:
                print(f"ERR: {e}")


if __name__ == "__main__":
    main()
