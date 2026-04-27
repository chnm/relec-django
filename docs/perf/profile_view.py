"""Capture SQL emitted by /census/browser/?page=11000.

Run inside the app container:
  docker cp scripts/perf/profile_view.py <project>-app-1:/app/profile_view.py
  docker exec <project>-app-1 sh -c "cd /app && uv run python profile_view.py"

Sets DEBUG=True so connection.queries is populated; clears the cache so
@cache_page entries don't short-circuit the view.
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


URL = os.environ.get("PROFILE_URL", "/census/browser/?page=11000")


def main():
    client = Client(HTTP_HOST="localhost", SERVER_NAME="localhost")
    cache.clear()
    print(f"Hitting {URL}")
    reset_queries()
    t0 = time.perf_counter()
    resp = client.get(URL)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"status={resp.status_code} elapsed={elapsed:.0f}ms "
          f"n_queries={len(connection.queries)}\n")

    qs = sorted(connection.queries, key=lambda q: -float(q["time"]))
    print("=== Top 10 slowest queries ===")
    for i, q in enumerate(qs[:10]):
        print(f"\n--- #{i+1}  {q['time']}s ---")
        sql = q["sql"]
        print(sql[:1200] + ("..." if len(sql) > 1200 else ""))

    sql_ms = sum(float(q["time"]) for q in connection.queries) * 1000
    print(f"\n=== Total wall: {elapsed:.0f}ms / SQL: {sql_ms:.0f}ms ===")


if __name__ == "__main__":
    main()
