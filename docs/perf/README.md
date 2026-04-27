# Performance scripts

Tools used to investigate why `/census/browser/` was slow under bot/scraper
load and to verify the fix landed in commit
`perf(census): drop blanket DISTINCT, use Exists, cache unfiltered count`.

Two categories:

| Script | Where it runs | What it does |
|---|---|---|
| `load.py` | Anywhere with HTTP access | Aggressive HTTP load (concurrent, no delay) against a target host. Two phases: REPEAT (5 URLs hammered) and UNIQUE (500 distinct URLs). |
| `analyze.py` | Anywhere | Reads `results.csv` produced by `load.py`. Reports latency percentiles, status mix, and Caddy cache `Age`-header breakdown per phase. |
| `profile_view.py` | Inside the app container | Hits `/census/browser/?page=11000` once via `django.test.Client` with `DEBUG=True`, prints the top-10 slowest queries with their SQL. |
| `profile_warm.py` | Inside the app container | Hits the view 3 times to verify the unfiltered-count cache is being reused. |
| `profile_filters.py` | Inside the app container | Hits each filter path (`?has_membership=yes`, `?urban_rural=urban`, state filter, search, denomination) and reports SQL time + slowest queries per path. |
| `explain.py` | Inside the app container | Runs the view once, captures the SQL for queries >100ms, then runs `EXPLAIN (ANALYZE, BUFFERS)` on each. Use this when you need the raw plan. |

## Running the blackbox load test

```bash
RELEC_HOST=https://dev.religiousecologies.org \
RELEC_OUT=/tmp/results.csv \
  python docs/perf/load.py
python docs/perf/analyze.py /tmp/results.csv
```

Defaults if env vars are unset: target `http://localhost:8000`, output
`./results.csv`. Honest UA is sent (`claude-code-scrape-sim/1.0`); change
the `UA` constant if you need to spoof a browser to bypass UA-based blocks.

## Running the in-container profilers

Copy the script into the running app container, then exec it:

```bash
PROJECT=relec-profile  # or the name of your compose project

docker cp docs/perf/profile_view.py ${PROJECT}-app-1:/app/profile_view.py
docker exec ${PROJECT}-app-1 sh -c "cd /app && uv run python profile_view.py"
```

Same pattern for `profile_warm.py`, `profile_filters.py`, `explain.py`.
All of them:

- Set `settings.DEBUG = True` so `connection.queries` is populated.
- Call `cache.clear()` at the top to force a cold render.
- Use `django.test.Client(HTTP_HOST="localhost")` to bypass `ALLOWED_HOSTS`.

## Reproducing the original investigation

The conclusion was that `Paginator(queryset.distinct(), 20)` made every cold
render run a 227,733-row sort+dedup over the full SELECT projection, costing
~1.3s on the page query and ~0.35s on the COUNT. The fix in `census/views.py`
makes `.distinct()` conditional, replaces the `has_membership` and
`urban_rural` join filters with `Exists` subqueries, and caches the
unfiltered total in Memcached.

Before/after on a `pg_restore`d copy of dev (227,733 census schedules):

| URL | Before | After cold | After warm |
|---|---:|---:|---:|
| `/census/browser/?page=11000` | 1.75s SQL | 571ms | 437ms |
| `/census/browser/CA/?page=10` | — | 149ms | — |
| `?has_membership=yes` | — | 250ms | — |

To reproduce against your own data:

1. `pg_dump -Fc` your prod DB, `pg_restore` into the compose `db` service.
2. Run `profile_view.py` on the unpatched code — capture baseline SQL time.
3. Apply the patch (or check out the branch).
4. Re-run `profile_view.py` and compare.
