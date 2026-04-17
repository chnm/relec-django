"""
Data reconciliation / sanity check command.

Compares data across three systems:
  1. Omeka API   (https://omeka.religiousecologies.org/api)  — source
  2. Django DB   (this project)                              — transcription system
  3. data.chnm.org                                           — published API

Key mappings used for matching:
  CensusSchedule.resource_id      ↔  Omeka o:id
  Denomination.denomination_id    ↔  Omeka mare:denominationId  ↔  data.chnm.org denomination_id
  County.ahcb_id                  ↔  Omeka mare:ahcbCountyId    ↔  data.chnm.org county_ahcb
  PopulatedPlace.place_id         ↔  data.chnm.org place_id

Output: a timestamped plain-text report written to the reports/ directory.

Usage:
    uv run python manage.py sanity_check
    uv run python manage.py sanity_check --output-dir /path/to/dir
    uv run python manage.py sanity_check --omeka-delay 1.0   # slower / politer
    uv run python manage.py sanity_check --omeka-per-page 50 # smaller pages
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from django.core.management.base import BaseCommand

from census.models import CensusSchedule, Denomination, ReligiousBody
from location.models import County, PopulatedPlace

OMEKA_API = "https://omeka.religiousecologies.org/api"
DATA_CHNM_API = "https://data.chnm.org"
OMEKA_SCHEDULE_CLASS_ID = 111  # mare:Schedule resource class
REPORT_WIDTH = 80


class Command(BaseCommand):
    help = "Reconcile data between Omeka, Django, and data.chnm.org — writes a text report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default="reports",
            help="Directory for the report file (default: reports/)",
        )
        parser.add_argument(
            "--omeka-delay",
            type=float,
            default=0.5,
            help="Seconds between Omeka API page requests (default: 0.5)",
        )
        parser.add_argument(
            "--omeka-per-page",
            type=int,
            default=100,
            help="Items per page when fetching from Omeka (default: 100)",
        )
        parser.add_argument(
            "--save-cache",
            type=str,
            default=None,
            metavar="FILE",
            help="Save fetched Omeka + chnm data to a JSON file for faster re-runs",
        )
        parser.add_argument(
            "--load-cache",
            type=str,
            default=None,
            metavar="FILE",
            help="Load previously cached Omeka + chnm data instead of re-fetching",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Entry point
    # ─────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        started_at = datetime.now()
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"reconciliation_{started_at.strftime('%Y%m%d_%H%M%S')}.txt"

        self.stdout.write(f"Starting reconciliation at {started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Report will be written to: {report_path}")
        self.stdout.write("")

        cache_file = options.get("load_cache")
        if cache_file:
            # ── Load from cache (skip Omeka + chnm fetches) ──────────────────
            cache_path = Path(cache_file)
            self.stdout.write(self.style.WARNING(f"Loading cached data from {cache_path} ..."))
            with open(cache_path) as fh:
                cached = json.load(fh)
            omeka_schedules = cached["omeka_schedules"]
            chnm_data = cached["chnm_data"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"  → {len(omeka_schedules):,} Omeka items and chnm data loaded from cache"
                )
            )
        else:
            # ── Phase 1: Omeka ────────────────────────────────────────────────
            self._section_header("PHASE 1: Fetching Omeka Schedule items")
            omeka_schedules = self._fetch_omeka_schedules(
                delay=options["omeka_delay"],
                per_page=options["omeka_per_page"],
            )
            self.stdout.write(
                self.style.SUCCESS(f"  → {len(omeka_schedules):,} Omeka schedule items fetched")
            )

            # ── Phase 3: data.chnm.org ────────────────────────────────────────
            self.stdout.write("")
            self._section_header("PHASE 3: Fetching data.chnm.org endpoints")
            chnm_data = self._fetch_chnm_data()

            # ── Optionally save cache ─────────────────────────────────────────
            if options.get("save_cache"):
                save_path = Path(options["save_cache"])
                self.stdout.write(f"  Saving cache to {save_path} ...")
                with open(save_path, "w") as fh:
                    json.dump({"omeka_schedules": omeka_schedules, "chnm_data": chnm_data}, fh)
                self.stdout.write(self.style.SUCCESS(f"  → Cache saved: {save_path}"))

        # ── Phase 2: Django DB ────────────────────────────────────────────────
        self.stdout.write("")
        self._section_header("PHASE 2: Querying Django database")
        django_data = self._collect_django_data()

        # ── Phase 4: Report ───────────────────────────────────────────────────
        self.stdout.write("")
        self._section_header("PHASE 4: Generating report")
        report = self._generate_report(
            started_at=started_at,
            omeka_schedules=omeka_schedules,
            django_data=django_data,
            chnm_data=chnm_data,
        )

        with open(report_path, "w") as fh:
            fh.write(report)

        elapsed = (datetime.now() - started_at).total_seconds()
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Done!  Report: {report_path}"))
        self.stdout.write(f"Total time: {elapsed / 60:.1f} minutes")

    # ─────────────────────────────────────────────────────────────────────────
    # Data collection
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_omeka_schedules(self, delay=0.5, per_page=100):
        """Page through Omeka and return a list of extracted schedule dicts."""
        url = f"{OMEKA_API}/items"
        params = {"resource_class_id": OMEKA_SCHEDULE_CLASS_ID, "per_page": per_page, "page": 1}
        all_items = []
        page = 1

        while True:
            params["page"] = page
            try:
                self.stdout.write(
                    f"  Page {page:>4}  ({len(all_items):,} items so far) ...", ending="\r"
                )
                resp = requests.get(url, params=params, timeout=30)
                resp.raise_for_status()
                items = resp.json()

                if not items:
                    self.stdout.write("")  # clear the \r line
                    break

                for item in items:
                    all_items.append(self._extract_omeka_fields(item))

                page += 1
                time.sleep(delay)

            except requests.exceptions.RequestException as exc:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR(f"  Omeka API error on page {page}: {exc}"))
                self.stdout.write(
                    self.style.WARNING("  Continuing with partial data — results may be incomplete.")
                )
                break

        self.stdout.write(
            f"  Fetched {len(all_items):,} items across {page - 1} page(s)"
        )
        return all_items

    def _extract_omeka_fields(self, item):
        """Pull the fields we care about from a raw Omeka item dict."""
        def val(prop):
            entries = item.get(prop, [])
            return entries[0].get("@value") if entries else None

        return {
            "omeka_id":        item.get("o:id"),
            "schedule_id":     val("mare:scheduleId"),
            "denomination_id": val("mare:denominationId"),
            "ahcb_county_id":  val("mare:ahcbCountyId"),
            "title":           item.get("o:title", ""),
            "is_public":       item.get("o:is_public", False),
        }

    def _collect_django_data(self):
        """Query the Django ORM and return everything we need for comparison."""
        self.stdout.write("  Collecting CensusSchedule records ...")
        schedules = list(
            CensusSchedule.objects.select_related(
                "county__state", "populated_place__county"
            ).values(
                "id", "resource_id", "schedule_id", "schedule_title",
                "transcription_status",
                "county__ahcb_id", "county__name", "county__state__code",
                "populated_place__id", "populated_place__place_id", "populated_place__name",
            )
        )
        self.stdout.write(f"    {len(schedules):,} CensusSchedule records")

        self.stdout.write("  Collecting Denomination records ...")
        denominations = list(
            Denomination.objects.values(
                "id", "denomination_id", "name", "short_name", "family_census", "family_relec"
            )
        )
        self.stdout.write(f"    {len(denominations):,} Denomination records")

        self.stdout.write("  Collecting County records ...")
        counties = list(
            County.objects.select_related("state").values("ahcb_id", "name", "state__code", "state__name")
        )
        self.stdout.write(f"    {len(counties):,} County records")

        self.stdout.write("  Collecting PopulatedPlace records ...")
        populated_places = list(
            PopulatedPlace.objects.select_related("county__state").values(
                "id", "place_id", "name", "county__ahcb_id", "county__state__code"
            )
        )
        self.stdout.write(f"    {len(populated_places):,} PopulatedPlace records")

        self.stdout.write("  Collecting ReligiousBody stats ...")
        from django.db.models import Count as DjCount
        rb_geocode = dict(
            ReligiousBody.objects.values_list("geocode_status").annotate(DjCount("id"))
        )
        rb_total = ReligiousBody.objects.count()
        self.stdout.write(f"    {rb_total:,} ReligiousBody records")

        return {
            "schedules":        schedules,
            "denominations":    denominations,
            "counties":         counties,
            "populated_places": populated_places,
            "rb_geocode":       rb_geocode,
            "rb_total":         rb_total,
        }

    def _fetch_chnm_data(self):
        """Fetch reference datasets from data.chnm.org."""
        result = {}
        endpoints = {
            "cities":               "/relcensus/cities",
            "denominations":        "/relcensus/denominations",
            "denomination_families":"/relcensus/denomination-families",
        }
        for key, path in endpoints.items():
            url = DATA_CHNM_API + path
            self.stdout.write(f"  Fetching {url} ...")
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                result[key] = resp.json()
                count = len(result[key]) if isinstance(result[key], list) else "1 object"
                self.stdout.write(f"    → {count} items")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"    Failed: {exc}"))
                result[key] = [] if key != "denomination_families" else {}

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Report generation
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_report(self, started_at, omeka_schedules, django_data, chnm_data):
        W = REPORT_WIDTH
        lines = []

        # ── helpers ────────────────────────────────────────────────────────
        def h1(title):
            lines.extend(["", "=" * W, title.center(W), "=" * W])

        def h2(title):
            lines.extend(["", title, "-" * min(len(title), W)])

        def h3(title):
            lines.extend(["", f"  {title}", f"  {'~' * min(len(title), W - 2)}"])

        def kv(label, value, indent=0):
            pad = "  " * indent
            lines.append(f"{pad}{label:<52} {value}")

        def note(text):
            lines.append(f"  NOTE: {text}")

        def blank():
            lines.append("")

        # ── Pre-compute sets ────────────────────────────────────────────────

        # Omeka
        omeka_ids         = {s["omeka_id"] for s in omeka_schedules}
        omeka_denom_ids   = {s["denomination_id"] for s in omeka_schedules if s["denomination_id"]}
        omeka_county_ids  = {s["ahcb_county_id"]  for s in omeka_schedules if s["ahcb_county_id"]}
        omeka_with_county = {s["omeka_id"] for s in omeka_schedules if s["ahcb_county_id"]}
        omeka_by_id       = {s["omeka_id"]: s for s in omeka_schedules}

        # Django schedules
        dj_schedules       = django_data["schedules"]
        dj_resource_ids    = {s["resource_id"] for s in dj_schedules}
        dj_by_rid          = {s["resource_id"]: s for s in dj_schedules}
        dj_denom_ids       = {d["denomination_id"] for d in django_data["denominations"] if d["denomination_id"]}
        dj_county_ahcb_ids = {c["ahcb_id"] for c in django_data["counties"]}
        dj_place_ids       = {p["place_id"] for p in django_data["populated_places"] if p["place_id"]}
        dj_with_county     = {s["resource_id"] for s in dj_schedules if s["county__ahcb_id"]}
        dj_with_place      = {s["resource_id"] for s in dj_schedules if s["populated_place__place_id"]}

        # Status breakdown
        status_counts = defaultdict(int)
        for s in dj_schedules:
            status_counts[s["transcription_status"]] += 1

        # data.chnm.org
        chnm_cities          = chnm_data.get("cities", [])
        chnm_denoms          = chnm_data.get("denominations", [])
        chnm_denom_ids       = {d["denomination_id"] for d in chnm_denoms if d.get("denomination_id")}
        chnm_place_ids       = {c["place_id"] for c in chnm_cities if c.get("place_id")}
        chnm_county_ahcb_ids = {c["county_ahcb"] for c in chnm_cities if c.get("county_ahcb")}
        chnm_place_by_id     = {c["place_id"]: c for c in chnm_cities if c.get("place_id")}

        # Derived sets used in multiple sections
        in_both                          = omeka_ids & dj_resource_ids
        in_omeka_not_django              = omeka_ids - dj_resource_ids
        in_django_not_omeka              = dj_resource_ids - omeka_ids
        omeka_has_county_in_both         = {oid for oid in in_both if omeka_by_id[oid]["ahcb_county_id"]}
        dj_missing_county_omeka_has      = omeka_has_county_in_both - dj_with_county
        denom_in_omeka_not_django        = omeka_denom_ids - dj_denom_ids
        denom_in_django_not_omeka        = dj_denom_ids - omeka_denom_ids
        denom_in_omeka_not_chnm          = omeka_denom_ids - chnm_denom_ids
        denom_in_chnm_not_django         = chnm_denom_ids - dj_denom_ids
        denom_in_django_not_chnm         = dj_denom_ids - chnm_denom_ids
        counties_in_omeka_not_django     = omeka_county_ids - dj_county_ahcb_ids
        places_in_chnm_not_django        = chnm_place_ids - dj_place_ids
        places_in_django_not_chnm        = dj_place_ids - chnm_place_ids
        chnm_counties_not_in_django      = chnm_county_ahcb_ids - dj_county_ahcb_ids

        # ── Header ─────────────────────────────────────────────────────────
        lines.append("=" * W)
        lines.append("RELIGIOUS ECOLOGIES  —  DATA RECONCILIATION REPORT".center(W))
        lines.append("=" * W)
        blank()
        lines.append(f"  Generated:  {started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Completed:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Sources:    (1) Omeka API   (2) Django DB   (3) data.chnm.org")
        blank()

        # ── Executive Summary ───────────────────────────────────────────────
        h1("EXECUTIVE SUMMARY")
        blank()

        schedule_diff = len(omeka_ids) - len(dj_resource_ids)
        schedule_ok   = schedule_diff == 0
        kv("Omeka Schedule items fetched:",        f"{len(omeka_ids):,}")
        kv("Django CensusSchedule records:",       f"{len(dj_resource_ids):,}")
        kv("Count match:",                         "YES ✓" if schedule_ok else f"NO ✗  (delta = {schedule_diff:+,})")
        kv("  In Omeka but not Django:",            f"{len(in_omeka_not_django):,}")
        kv("  In Django but not Omeka:",            f"{len(in_django_not_omeka):,}")
        blank()

        pct = lambda n, d: f"{n:,}  ({n/max(d,1)*100:.1f}%)"
        kv("Schedules w/ county in Omeka (mare:ahcbCountyId):", pct(len(omeka_with_county), len(omeka_ids)))
        kv("Schedules w/ county in Django (FK set):",           pct(len(dj_with_county),    len(dj_resource_ids)))
        kv("Django schedules missing county Omeka has:",        f"{len(dj_missing_county_omeka_has):,}")
        blank()
        kv("Django schedules with populated_place linked:",     pct(len(dj_with_place), len(dj_resource_ids)))
        kv("PopulatedPlace records in Django:",                 f"{len(dj_place_ids):,}")
        kv("Cities in data.chnm.org /relcensus/cities:",        f"{len(chnm_place_ids):,}")
        kv("  In data.chnm.org but NOT in Django:",             f"{len(places_in_chnm_not_django):,}")
        kv("  In Django but NOT in data.chnm.org:",             f"{len(places_in_django_not_chnm):,}")
        blank()
        kv("Denomination IDs referenced in Omeka schedules:",   f"{len(omeka_denom_ids):,}")
        kv("Denomination records in Django:",                   f"{len(dj_denom_ids):,}")
        kv("Denomination records in data.chnm.org:",            f"{len(chnm_denom_ids):,}")
        kv("  Omeka denom IDs not in Django:",                  f"{len(denom_in_omeka_not_django):,}")
        kv("  Django denom IDs not in data.chnm.org:",          f"{len(denom_in_django_not_chnm):,}")
        blank()
        kv("ReligiousBody total records:",                      f"{django_data['rb_total']:,}")
        for gs, gc in sorted(django_data["rb_geocode"].items(), key=lambda x: (x[0] is None, x[0] or "")):
            kv(f"  geocode_status = '{gs}':", f"{gc:,}")

        # ── Section 1: Schedule Counts ──────────────────────────────────────
        h1("SECTION 1: SCHEDULE COUNTS")

        h2("1.1  Totals")
        blank()
        kv("Omeka Schedule items (resource_class_id=111):", f"{len(omeka_ids):,}")
        kv("Django CensusSchedule records:",                f"{len(dj_resource_ids):,}")
        kv("Difference (Omeka − Django):",                  f"{schedule_diff:+,}")

        h2("1.2  Transcription Status Breakdown (Django)")
        blank()
        ordered_statuses = [
            "unassigned", "assigned", "in_progress",
            "needs_review", "completed", "approved",
        ]
        for st in ordered_statuses:
            cnt = status_counts.get(st, 0)
            kv(f"  {st}:", f"{cnt:>6,}  ({cnt/max(len(dj_resource_ids),1)*100:.1f}%)")
        for st in sorted(set(status_counts) - set(ordered_statuses)):
            cnt = status_counts[st]
            kv(f"  {st} (unexpected):", f"{cnt:>6,}")
        kv("  TOTAL:", f"{len(dj_resource_ids):>6,}")

        h2("1.3  In Omeka but NOT in Django")
        blank()
        kv("Count:", f"{len(in_omeka_not_django):,}")
        if in_omeka_not_django:
            blank()
            lines.append(f"  {'Omeka ID':<10}  {'Schedule ID':<22}  {'Denom ID':<20}  {'County AHCB':<22}  Public")
            lines.append("  " + "-" * 82)
            for oid in sorted(in_omeka_not_django):
                s = omeka_by_id[oid]
                lines.append(
                    f"  {oid:<10}  {str(s['schedule_id'] or ''):<22}  "
                    f"{str(s['denomination_id'] or ''):<20}  "
                    f"{str(s['ahcb_county_id'] or ''):<22}  "
                    f"{'Yes' if s['is_public'] else 'No'}"
                )
        else:
            lines.append("  (none — all Omeka schedules have a matching Django record)")

        h2("1.4  In Django but NOT in Omeka")
        blank()
        kv("Count:", f"{len(in_django_not_omeka):,}")
        if in_django_not_omeka:
            blank()
            lines.append(f"  {'Resource ID':<12}  {'Schedule Title':<48}  Status")
            lines.append("  " + "-" * 75)
            for rid in sorted(in_django_not_omeka):
                s = dj_by_rid.get(rid, {})
                title  = (s.get("schedule_title") or "")[:46]
                status = s.get("transcription_status", "")
                lines.append(f"  {rid:<12}  {title:<48}  {status}")
        else:
            lines.append("  (none — all Django schedules exist in Omeka)")

        # ── Section 2: Denomination Reconciliation ──────────────────────────
        h1("SECTION 2: DENOMINATION RECONCILIATION")

        h2("2.1  Summary")
        blank()
        kv("Denomination IDs in Omeka schedules:",    f"{len(omeka_denom_ids):,}")
        kv("Denomination records in Django:",         f"{len(dj_denom_ids):,}")
        kv("Denomination records in data.chnm.org:",  f"{len(chnm_denom_ids):,}")
        blank()
        kv("In Omeka but NOT in Django:",             f"{len(denom_in_omeka_not_django):,}")
        kv("In Django but NOT in Omeka:",             f"{len(denom_in_django_not_omeka):,}")
        kv("In Omeka but NOT in data.chnm.org:",      f"{len(denom_in_omeka_not_chnm):,}")
        kv("In data.chnm.org but NOT in Django:",     f"{len(denom_in_chnm_not_django):,}")
        kv("In Django but NOT in data.chnm.org:",     f"{len(denom_in_django_not_chnm):,}")

        h2("2.2  Denomination IDs in Omeka schedules but NOT in Django")
        blank()
        kv("Count:", f"{len(denom_in_omeka_not_django):,}")
        if denom_in_omeka_not_django:
            note("These denomination_ids appear on Omeka Schedule items but have no matching")
            note("Denomination record in Django. Schedules using these IDs may be mis-linked")
            note("or the denomination import may be incomplete.")
            blank()
            omeka_denom_sched_count = defaultdict(int)
            for s in omeka_schedules:
                if s["denomination_id"] in denom_in_omeka_not_django:
                    omeka_denom_sched_count[s["denomination_id"]] += 1
            lines.append(f"  {'Denomination ID':<28}  Schedules Affected")
            lines.append("  " + "-" * 50)
            for did in sorted(denom_in_omeka_not_django):
                lines.append(f"  {did:<28}  {omeka_denom_sched_count[did]:,}")
        else:
            lines.append("  (none — all Omeka denomination IDs exist in Django)")

        h2("2.3  Django Denomination IDs NOT referenced in any Omeka schedule")
        blank()
        kv("Count:", f"{len(denom_in_django_not_omeka):,}")
        if denom_in_django_not_omeka:
            note("These denominations exist in Django but no Omeka schedule references them.")
            blank()
            denom_by_id = {d["denomination_id"]: d for d in django_data["denominations"]}
            lines.append(f"  {'Denomination ID':<28}  Name")
            lines.append("  " + "-" * 70)
            for did in sorted(denom_in_django_not_omeka):
                d = denom_by_id.get(did, {})
                lines.append(f"  {did:<28}  {(d.get('name') or '')[:40]}")
        else:
            lines.append("  (none — all Django denominations appear in Omeka schedules)")

        h2("2.4  Denomination IDs in data.chnm.org but NOT in Django")
        blank()
        kv("Count:", f"{len(denom_in_chnm_not_django):,}")
        if denom_in_chnm_not_django:
            chnm_denom_by_id = {d["denomination_id"]: d for d in chnm_denoms if d.get("denomination_id")}
            lines.append(f"  {'Denomination ID':<28}  Name (data.chnm.org)")
            lines.append("  " + "-" * 70)
            for did in sorted(denom_in_chnm_not_django):
                d = chnm_denom_by_id.get(did, {})
                lines.append(f"  {did:<28}  {(d.get('name') or '')[:40]}")
        else:
            lines.append("  (none)")

        h2("2.5  Django Denomination IDs NOT in data.chnm.org")
        blank()
        kv("Count:", f"{len(denom_in_django_not_chnm):,}")
        if denom_in_django_not_chnm:
            denom_by_id = {d["denomination_id"]: d for d in django_data["denominations"]}
            lines.append(f"  {'Denomination ID':<28}  Name (Django)")
            lines.append("  " + "-" * 70)
            for did in sorted(denom_in_django_not_chnm):
                d = denom_by_id.get(did, {})
                lines.append(f"  {did:<28}  {(d.get('name') or '')[:40]}")
        else:
            lines.append("  (none — all Django denominations are in data.chnm.org)")

        h2("2.6  Denomination ID mismatch: Omeka vs data.chnm.org")
        blank()
        kv("Count (in Omeka but NOT in data.chnm.org):", f"{len(denom_in_omeka_not_chnm):,}")
        if denom_in_omeka_not_chnm:
            for did in sorted(denom_in_omeka_not_chnm):
                lines.append(f"    - {did}")
        else:
            lines.append("  (none)")

        # ── Section 3: County Coverage ──────────────────────────────────────
        h1("SECTION 3: COUNTY COVERAGE")

        h2("3.1  Coverage Summary")
        blank()
        kv("Omeka schedules with mare:ahcbCountyId:",
           pct(len(omeka_with_county), len(omeka_ids)))
        kv("Django schedules with county FK set:",
           pct(len(dj_with_county), len(dj_resource_ids)))
        kv("Django schedules missing county where Omeka has it:",
           f"{len(dj_missing_county_omeka_has):,}")
        blank()
        kv("Distinct AHCB county IDs in Omeka schedules:",   f"{len(omeka_county_ids):,}")
        kv("County records in Django:",                      f"{len(dj_county_ahcb_ids):,}")
        kv("Distinct county_ahcb values in data.chnm.org:",  f"{len(chnm_county_ahcb_ids):,}")

        h2("3.2  County AHCB IDs in Omeka but NOT in Django County table")
        blank()
        kv("Count:", f"{len(counties_in_omeka_not_django):,}")
        if counties_in_omeka_not_django:
            note("Schedules with these county IDs cannot be linked to a County in Django.")
            blank()
            missing_county_sched_count = defaultdict(int)
            for s in omeka_schedules:
                if s["ahcb_county_id"] in counties_in_omeka_not_django:
                    missing_county_sched_count[s["ahcb_county_id"]] += 1
            lines.append(f"  {'AHCB County ID':<32}  Schedules Affected")
            lines.append("  " + "-" * 52)
            for ahcb in sorted(counties_in_omeka_not_django):
                lines.append(f"  {ahcb:<32}  {missing_county_sched_count[ahcb]:,}")
        else:
            lines.append("  (none — all Omeka county IDs exist in Django)")

        h2("3.3  County AHCB IDs in data.chnm.org but NOT in Django County table")
        blank()
        kv("Count:", f"{len(chnm_counties_not_in_django):,}")
        if chnm_counties_not_in_django:
            for ahcb in sorted(chnm_counties_not_in_django):
                lines.append(f"    - {ahcb}")
        else:
            lines.append("  (none)")

        h2("3.4  Django Schedules Missing County (Where Omeka Has County Data)")
        blank()
        kv("Count:", f"{len(dj_missing_county_omeka_has):,}")
        if dj_missing_county_omeka_has:
            note("Omeka has a county AHCB ID for these schedules, but the Django county FK")
            note("is not set. Running `link_counties_from_omeka` should resolve these.")
            blank()
            lines.append(
                f"  {'Omeka ID':<10}  {'Schedule ID':<22}  {'AHCB County (Omeka)':<26}  Django Status"
            )
            lines.append("  " + "-" * 80)
            shown = 0
            for oid in sorted(dj_missing_county_omeka_has):
                if shown >= 150:
                    remaining = len(dj_missing_county_omeka_has) - shown
                    lines.append(f"  ... {remaining:,} more — see Appendix A for full list")
                    break
                s  = omeka_by_id[oid]
                ds = dj_by_rid.get(oid, {})
                lines.append(
                    f"  {oid:<10}  {str(s['schedule_id'] or ''):<22}  "
                    f"{str(s['ahcb_county_id'] or ''):<26}  "
                    f"{ds.get('transcription_status', '?')}"
                )
                shown += 1
        else:
            lines.append("  (none — county linkage is complete for all matched schedules)")

        h2("3.5  County Coverage Breakdown by State (Django schedules)")
        blank()
        state_county_counts = defaultdict(lambda: {"with": 0, "without": 0})
        for s in dj_schedules:
            state = s.get("county__state__code") or "(unlinked)"
            if s["county__ahcb_id"]:
                state_county_counts[state]["with"] += 1
            else:
                state_county_counts[state]["without"] += 1
        lines.append(f"  {'State':<8}  {'W/ County':>9}  {'No County':>9}  {'Total':>7}  {'Coverage':>9}")
        lines.append("  " + "-" * 52)
        for state in sorted(state_county_counts):
            wc    = state_county_counts[state]["with"]
            nc    = state_county_counts[state]["without"]
            tot   = wc + nc
            lines.append(f"  {state:<8}  {wc:>9,}  {nc:>9,}  {tot:>7,}  {wc/max(tot,1)*100:>8.1f}%")

        # ── Section 4: Populated Place Coverage ────────────────────────────
        h1("SECTION 4: POPULATED PLACE COVERAGE")

        h2("4.1  Coverage Summary")
        blank()
        kv("Django schedules with populated_place linked:",
           pct(len(dj_with_place), len(dj_resource_ids)))
        kv("PopulatedPlace records in Django:",         f"{len(django_data['populated_places']):,}")
        kv("  With a place_id value (non-null):",       f"{len(dj_place_ids):,}")
        kv("  With no place_id (null):",
           f"{sum(1 for p in django_data['populated_places'] if not p['place_id']):,}")
        blank()
        kv("Cities in data.chnm.org /relcensus/cities:",     f"{len(chnm_place_ids):,}")
        kv("  In data.chnm.org but NOT in Django:",          f"{len(places_in_chnm_not_django):,}")
        kv("  In Django but NOT in data.chnm.org:",          f"{len(places_in_django_not_chnm):,}")

        h2("4.2  Place IDs in data.chnm.org but NOT in Django PopulatedPlace")
        blank()
        kv("Count:", f"{len(places_in_chnm_not_django):,}")
        if places_in_chnm_not_django:
            note("These place_ids exist in data.chnm.org but not in Django's PopulatedPlace table.")
            blank()
            lines.append(f"  {'Place ID':<12}  {'City':<36}  {'State':<6}  County")
            lines.append("  " + "-" * 75)
            shown = 0
            for pid in sorted(places_in_chnm_not_django):
                if shown >= 100:
                    lines.append(f"  ... {len(places_in_chnm_not_django)-shown:,} more — see Appendix B")
                    break
                c = chnm_place_by_id.get(pid, {})
                lines.append(
                    f"  {pid:<12}  {(c.get('city',''))[:35]:<36}  "
                    f"{c.get('state',''):<6}  {(c.get('county',''))[:25]}"
                )
                shown += 1
        else:
            lines.append("  (none — all data.chnm.org cities are in Django)")

        h2("4.3  Place IDs in Django PopulatedPlace but NOT in data.chnm.org")
        blank()
        kv("Count:", f"{len(places_in_django_not_chnm):,}")
        if places_in_django_not_chnm:
            note("These Django PopulatedPlace records have a place_id not in data.chnm.org.")
            blank()
            dj_pp_by_id = {p["place_id"]: p for p in django_data["populated_places"] if p["place_id"]}
            lines.append(f"  {'Place ID':<12}  {'Name':<36}  {'State':<6}  County AHCB")
            lines.append("  " + "-" * 75)
            shown = 0
            for pid in sorted(places_in_django_not_chnm):
                if shown >= 100:
                    lines.append(f"  ... {len(places_in_django_not_chnm)-shown:,} more — see Appendix C")
                    break
                p = dj_pp_by_id.get(pid, {})
                lines.append(
                    f"  {pid:<12}  {(p.get('name',''))[:35]:<36}  "
                    f"{p.get('county__state__code',''):<6}  {(p.get('county__ahcb_id',''))[:25]}"
                )
                shown += 1
        else:
            lines.append("  (none — all Django place_ids are in data.chnm.org)")

        h2("4.4  Populated Place Coverage by State (Django schedules)")
        blank()
        state_place_counts = defaultdict(lambda: {"with": 0, "without": 0})
        for s in dj_schedules:
            state = s.get("county__state__code") or "(unlinked)"
            if s["populated_place__place_id"]:
                state_place_counts[state]["with"] += 1
            else:
                state_place_counts[state]["without"] += 1
        lines.append(f"  {'State':<8}  {'W/ Place':>8}  {'No Place':>8}  {'Total':>7}  {'Coverage':>9}")
        lines.append("  " + "-" * 50)
        for state in sorted(state_place_counts):
            wp  = state_place_counts[state]["with"]
            np_ = state_place_counts[state]["without"]
            tot = wp + np_
            lines.append(
                f"  {state:<8}  {wp:>8,}  {np_:>8,}  {tot:>7,}  {wp/max(tot,1)*100:>8.1f}%"
            )

        # ── Section 5: data.chnm.org Cross-Check ───────────────────────────
        h1("SECTION 5: DATA.CHNM.ORG CROSS-CHECK")

        h2("5.1  Summary")
        blank()
        kv("data.chnm.org /relcensus/cities:",               f"{len(chnm_cities):,} records")
        kv("data.chnm.org /relcensus/denominations:",         f"{len(chnm_denoms):,} records")
        fam_data = chnm_data.get("denomination_families", {})
        if isinstance(fam_data, dict):
            fam_relec  = len(fam_data.get("family_relec", []))
            fam_census = len(fam_data.get("family_census", []))
            kv("data.chnm.org /relcensus/denomination-families:",
               f"{fam_relec} family_relec  /  {fam_census} family_census")

        h2("5.2  Denomination ID alignment across all three systems")
        blank()
        all_denom_ids = omeka_denom_ids | dj_denom_ids | chnm_denom_ids
        lines.append(f"  {'Denomination ID':<28}  Omeka  Django  data.chnm.org")
        lines.append("  " + "-" * 60)
        discrepancies = []
        for did in sorted(all_denom_ids):
            in_o = "  ✓   " if did in omeka_denom_ids else "  ✗   "
            in_d = "  ✓   " if did in dj_denom_ids    else "  ✗   "
            in_c = "      ✓" if did in chnm_denom_ids  else "      ✗"
            if not (did in omeka_denom_ids and did in dj_denom_ids and did in chnm_denom_ids):
                discrepancies.append((did, in_o, in_d, in_c))
        if discrepancies:
            for did, in_o, in_d, in_c in discrepancies:
                lines.append(f"  {did:<28} {in_o} {in_d} {in_c}")
        else:
            lines.append("  All denomination IDs are consistent across all three systems ✓")

        # ── Appendix A: Full missing-county list ────────────────────────────
        h1("APPENDIX A: DJANGO SCHEDULES MISSING COUNTY (OMEKA HAS COUNTY DATA)")
        blank()
        kv("Total count:", f"{len(dj_missing_county_omeka_has):,}")
        blank()
        if dj_missing_county_omeka_has:
            lines.append(
                f"  {'Omeka ID':<10}  {'Schedule ID':<24}  {'AHCB County (Omeka)':<28}  Django Status"
            )
            lines.append("  " + "-" * 82)
            for oid in sorted(dj_missing_county_omeka_has):
                s  = omeka_by_id[oid]
                ds = dj_by_rid.get(oid, {})
                lines.append(
                    f"  {oid:<10}  {str(s['schedule_id'] or ''):<24}  "
                    f"{str(s['ahcb_county_id'] or ''):<28}  "
                    f"{ds.get('transcription_status', '?')}"
                )
        else:
            lines.append("  (none)")

        # ── Appendix B: Full places-in-chnm-not-django list ─────────────────
        h1("APPENDIX B: PLACE IDs IN DATA.CHNM.ORG NOT IN DJANGO")
        blank()
        kv("Total count:", f"{len(places_in_chnm_not_django):,}")
        blank()
        if places_in_chnm_not_django:
            lines.append(f"  {'Place ID':<12}  {'City':<36}  {'State':<6}  County")
            lines.append("  " + "-" * 75)
            for pid in sorted(places_in_chnm_not_django):
                c = chnm_place_by_id.get(pid, {})
                lines.append(
                    f"  {pid:<12}  {(c.get('city',''))[:35]:<36}  "
                    f"{c.get('state',''):<6}  {(c.get('county',''))[:28]}"
                )
        else:
            lines.append("  (none)")

        # ── Appendix C: Full places-in-django-not-chnm list ─────────────────
        h1("APPENDIX C: PLACE IDs IN DJANGO NOT IN DATA.CHNM.ORG")
        blank()
        kv("Total count:", f"{len(places_in_django_not_chnm):,}")
        blank()
        if places_in_django_not_chnm:
            dj_pp_by_id = {p["place_id"]: p for p in django_data["populated_places"] if p["place_id"]}
            lines.append(f"  {'Place ID':<12}  {'Name':<36}  {'State':<6}  County AHCB")
            lines.append("  " + "-" * 75)
            for pid in sorted(places_in_django_not_chnm):
                p = dj_pp_by_id.get(pid, {})
                lines.append(
                    f"  {pid:<12}  {(p.get('name',''))[:35]:<36}  "
                    f"{p.get('county__state__code',''):<6}  {(p.get('county__ahcb_id',''))[:28]}"
                )
        else:
            lines.append("  (none)")

        # ── Footer ──────────────────────────────────────────────────────────
        blank()
        lines.append("=" * W)
        lines.append("END OF REPORT".center(W))
        lines.append("=" * W)

        return "\n".join(lines) + "\n"

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    def _section_header(self, title):
        self.stdout.write(f"\n{'─' * 60}")
        self.stdout.write(title)
        self.stdout.write(f"{'─' * 60}")
