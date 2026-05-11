"""
Build the DC Churches data layers from source datasets.

This command processes the original source CSVs for the 1926 and 2019
DC churches data, links them to CensusSchedule records, matches churches
across the two datasets, and produces import-ready export CSVs.

Source files (in static-data/):
    dc-churches.csv              -- 1926 churches with resource_id
    dc-churches_all-churches.csv -- Researcher spreadsheet with denominations
    Places_of_Worship.csv        -- 2019 DC Open Data export (Web Mercator coords)

Output files (in static-data/):
    dc-churches-export.csv       -- Import-ready 1926 DataLayer CSV
    dc-churches-2019-export.csv  -- Import-ready 2019 DataLayer CSV
    dc-churches-matched.csv      -- Matched pairs for researcher review

Usage:
    uv run python manage.py build_dc_churches           # full pipeline
    uv run python manage.py build_dc_churches --step link    # only link schedules
    uv run python manage.py build_dc_churches --step match   # only match 1926/2019
    uv run python manage.py build_dc_churches --step export  # only export CSVs
"""

import csv
import json
import math
import re
from pathlib import Path

from django.core.management.base import BaseCommand

from census.models import CensusSchedule, Denomination
from datalayers.models import DataLayer

STATIC_DATA = Path(__file__).resolve().parents[3] / "static-data"

# Denomination names that don't fuzzy-match well to DB Denomination.name
MANUAL_FAMILY_MAP = {
    "jewish": "Jewish",
    "congregational": "Congregational",
    "presbyterian": "Presbyterian",
    "protestant episcopal": "Episcopalian",
    "evangelical lutheran": "Lutheran",
    "salvation army": "Other groups",
    "christadelphians": "Restorationist",
    "eastern orthodox catholic church": "Orthodox",
    "interdenominational": "Other groups",
    "liberal catholic church": "Old Catholic",
    "baha'i": "Other groups",
    "presbyterian church in the united states (southern)": "Presbyterian",
    "lutheran (english)": "Lutheran",
    "universalist": "Other groups",
}


def normalize_addr(addr):
    if not addr:
        return ""
    addr = addr.upper().strip()
    for full, abbr in [
        ("STREET", "ST"), ("AVENUE", "AVE"), ("ROAD", "RD"),
        ("DRIVE", "DR"), ("BOULEVARD", "BLVD"), ("PLACE", "PL"),
        ("COURT", "CT"), ("NORTH", "N"), ("SOUTH", "S"),
        ("EAST", "E"), ("WEST", "W"),
    ]:
        addr = re.sub(rf"\b{full}\b", abbr, addr)
    addr = re.sub(r"[^A-Z0-9 ]", "", addr)
    addr = re.sub(r"\b(DC|WASHINGTON)\b", "", addr)
    return " ".join(addr.split())


def normalize_name(name):
    name = name.upper().strip()
    name = re.sub(r"'", "", name)
    name = re.sub(r"\bST\.?\b", "SAINT", name)
    name = re.sub(r"[^A-Z0-9 ]", "", name)
    for word in ["CHURCH", "THE", "OF", "AND", "MEMORIAL", "DC", "NW", "NE", "SE", "SW", "WASHINGTON"]:
        name = re.sub(rf"\b{word}\b", "", name)
    return " ".join(name.split())


def name_words(name):
    return set(normalize_name(name).split())


def mercator_to_latlng(x, y):
    lon = x / 20037508.34 * 180
    lat = y / 20037508.34 * 180
    lat = 180 / math.pi * (2 * math.atan(math.exp(lat * math.pi / 180)) - math.pi / 2)
    return lat, lon


class Command(BaseCommand):
    help = "Build DC Churches data layers from source datasets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--step",
            choices=["link", "import2019", "match", "export", "all"],
            default="all",
            help="Run a specific step (default: all)",
        )

    def handle(self, *args, **options):
        step = options["step"]
        if step in ("all", "link"):
            self._link_1926_schedules()
            self._apply_denomination_overrides()
        if step in ("all", "import2019"):
            self._import_2019()
        if step in ("all", "match"):
            self._match_datasets()
        if step in ("all", "export"):
            self._export_csvs()

    def _link_1926_schedules(self):
        """Link dc-churches DataLayer records to CensusSchedule via resource_id."""
        self.stdout.write("Linking 1926 schedules...")

        csv_path = STATIC_DATA / "dc-churches.csv"
        schedule_map = {}
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                rid = row.get("resource_id", "").strip()
                if rid:
                    schedule_map[row["title"]] = int(rid)

        linked = 0
        for dl in DataLayer.objects.filter(source="dc-churches"):
            rid = schedule_map.get(dl.title)
            if not rid:
                continue
            cs = CensusSchedule.objects.filter(resource_id=rid).first()
            if cs:
                dl.census_schedule = cs
                dl.save(update_fields=["census_schedule", "updated_at"])
                linked += 1

        self.stdout.write(self.style.SUCCESS(f"  Linked {linked} of {len(schedule_map)} records"))

    def _apply_denomination_overrides(self):
        """Apply denomination family from all-churches spreadsheet for unlinked records."""
        self.stdout.write("Applying denomination overrides...")

        ref_path = STATIC_DATA / "dc-churches_all-churches.csv"
        if not ref_path.exists():
            self.stdout.write(self.style.WARNING("  Skipped: dc-churches_all-churches.csv not found"))
            return

        # Parse reference spreadsheet
        ref = {}
        with open(ref_path) as f:
            for row in csv.DictReader(f):
                name = row["Church Name"]
                denom = row.get("Denomination", "").strip().split(":")[0].strip()
                clean = re.sub(r"\s*\(\d+\)", "", name).strip()
                ref[clean.lower()] = denom

        # Build DB denomination -> family lookup
        denom_to_family = {d.name.lower(): d.family_relec for d in Denomination.objects.all()}

        def get_family(denom_name):
            dl = denom_name.lower().replace("seventh day", "seventh-day")
            if dl in MANUAL_FAMILY_MAP:
                return MANUAL_FAMILY_MAP[dl]
            for db_name, fam in denom_to_family.items():
                if dl in db_name or db_name in dl:
                    return fam
            return None

        updated = 0
        for dl in DataLayer.objects.filter(source="dc-churches"):
            # Skip if already has denomination from linked schedule
            if dl.census_schedule_id:
                cs = dl.census_schedule
                if cs.schedule_denomination:
                    # Still check if denomination is null on the schedule
                    if cs.schedule_denomination.family_relec:
                        continue

            data = dl.data or {}
            if data.get("denomination_family_override"):
                continue

            # Find denomination in reference
            clean_title = re.sub(r"\s*\(.*?\)", "", dl.title).split(":")[0].strip().lower()
            denom = ref.get(dl.title.lower()) or ref.get(clean_title)
            if not denom:
                for k, v in ref.items():
                    if clean_title[:15] in k or k[:15] in clean_title:
                        denom = v
                        break

            if not denom:
                continue

            family = get_family(denom)
            if family:
                data["denomination_override"] = denom
                data["denomination_family_override"] = family
                dl.data = data
                dl.save(update_fields=["data", "updated_at"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"  Applied {updated} denomination overrides"))

    def _import_2019(self):
        """Import 2019 Places of Worship from DC Open Data CSV."""
        self.stdout.write("Importing 2019 data...")

        csv_path = STATIC_DATA / "Places_of_Worship.csv"
        if not csv_path.exists():
            self.stdout.write(self.style.WARNING("  Skipped: Places_of_Worship.csv not found"))
            return

        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        created = 0
        for r in rows:
            lat, lon = mercator_to_latlng(float(r["X"]), float(r["Y"]))
            data = {}
            if r.get("RELIGION", "").strip():
                data["religion"] = r["RELIGION"].strip().title()
            if r.get("PLACE_OF_WORSHIP", "").strip():
                data["place_type"] = r["PLACE_OF_WORSHIP"].strip().title()
            if r.get("WEB_URL", "").strip() and r["WEB_URL"] != "<Null>":
                data["web_url"] = r["WEB_URL"].strip()
            if r.get("ADDRESS", "").strip():
                data["address"] = r["ADDRESS"].strip()

            _, was_created = DataLayer.objects.update_or_create(
                title=r["NAME"].strip(),
                source="dc-churches-2019",
                defaults={
                    "lat": lat,
                    "lon": lon,
                    "county": "District of Columbia",
                    "state": "District of Columbia",
                    "data": data,
                },
            )
            if was_created:
                created += 1

        total = DataLayer.objects.filter(source="dc-churches-2019").count()
        self.stdout.write(self.style.SUCCESS(f"  Created {created}, total {total}"))

    def _match_datasets(self):
        """Match 1926 and 2019 churches by address and name."""
        self.stdout.write("Matching 1926 <-> 2019...")

        churches_1926 = list(DataLayer.objects.filter(source="dc-churches"))
        churches_2019 = list(DataLayer.objects.filter(source="dc-churches-2019"))

        if not churches_2019:
            self.stdout.write(self.style.WARNING("  No 2019 data found, skipping"))
            return

        # Build address lookup
        addr_to_2019 = {}
        for dl in churches_2019:
            a = normalize_addr((dl.data or {}).get("address", ""))
            if a:
                addr_to_2019.setdefault(a, []).append(dl)

        # Build name lookup
        name_to_2019 = {}
        for dl in churches_2019:
            n = normalize_name(dl.title)
            name_to_2019.setdefault(n, []).append(dl)

        matched = {}  # 1926 id -> (2019 DataLayer, method)
        used_2019 = set()

        # Pass 1: Full normalized address match
        for dl in churches_1926:
            a = normalize_addr((dl.data or {}).get("address", ""))
            if a and a in addr_to_2019:
                for dl2 in addr_to_2019[a]:
                    if dl2.id not in used_2019:
                        matched[dl.id] = (dl2, "address")
                        used_2019.add(dl2.id)
                        break

        self.stdout.write(f"  Pass 1 (address): {len(matched)}")

        # Pass 2: Exact normalized name
        for dl in churches_1926:
            if dl.id in matched:
                continue
            n = normalize_name(dl.title)
            if n in name_to_2019:
                for dl2 in name_to_2019[n]:
                    if dl2.id not in used_2019:
                        matched[dl.id] = (dl2, "name_exact")
                        used_2019.add(dl2.id)
                        break

        self.stdout.write(f"  Pass 2 (+name exact): {len(matched)}")

        # Pass 3: 2+ word name overlap
        for dl in churches_1926:
            if dl.id in matched:
                continue
            words1 = name_words(dl.title)
            if len(words1) < 2:
                continue
            best = None
            best_score = 0
            for dl2 in churches_2019:
                if dl2.id in used_2019:
                    continue
                overlap = words1 & name_words(dl2.title)
                if len(overlap) >= 2 and len(overlap) > best_score:
                    best_score = len(overlap)
                    best = dl2
            if best:
                matched[dl.id] = (best, "name_overlap")
                used_2019.add(best.id)

        self.stdout.write(f"  Pass 3 (+name overlap): {len(matched)}")

        # Store matches on both sides
        id_to_1926 = {dl.id: dl for dl in churches_1926}
        reverse = {v[0].id: k for k, v in matched.items()}

        for dl in churches_1926:
            data = dl.data or {}
            # Clear old match data
            for key in ["matched_2019_title", "matched_2019_id", "match_method"]:
                data.pop(key, None)
            if dl.id in matched:
                dl2, method = matched[dl.id]
                data["matched_2019_title"] = dl2.title
                data["matched_2019_id"] = dl2.id
                data["match_method"] = method
                data["match_status"] = "matched"
            else:
                data["match_status"] = "1926_only"
            dl.data = data
            dl.save(update_fields=["data", "updated_at"])

        for dl2 in churches_2019:
            data = dl2.data or {}
            for key in ["matched_1926_title", "matched_1926_id"]:
                data.pop(key, None)
            match_1926_id = reverse.get(dl2.id)
            if match_1926_id:
                dl1926 = id_to_1926[match_1926_id]
                data["matched_1926_title"] = dl1926.title
                data["matched_1926_id"] = dl1926.id
                data["match_status"] = "matched"
            else:
                data["match_status"] = "2019_only"
            dl2.data = data
            dl2.save(update_fields=["data", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"  Total matched: {len(matched)}, "
            f"1926 only: {len(churches_1926) - len(matched)}, "
            f"2019 only: {len(churches_2019) - len(reverse)}"
        ))

    def _export_csvs(self):
        """Export import-ready CSVs and a matched-pairs CSV for review."""
        self.stdout.write("Exporting CSVs...")

        fieldnames = ["title", "lat", "lon", "city", "county", "state", "source", "resource_id", "data"]

        for source in ["dc-churches", "dc-churches-2019"]:
            rows = []
            for dl in DataLayer.objects.filter(source=source).select_related("census_schedule").order_by("title"):
                row = {
                    "title": dl.title,
                    "lat": dl.lat,
                    "lon": dl.lon,
                    "city": dl.city,
                    "county": dl.county,
                    "state": dl.state,
                    "source": dl.source,
                    "resource_id": dl.census_schedule.resource_id if dl.census_schedule_id else "",
                    "data": json.dumps(dl.data) if dl.data else "{}",
                }
                rows.append(row)

            path = STATIC_DATA / f"{source}-export.csv"
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f"  {path.name}: {len(rows)} rows")

        # Matched pairs CSV for researcher review
        match_fieldnames = [
            "church_name_1926", "resource_id", "church_name_2019", "match_method",
            "denomination_1926", "denomination_family", "religion_2019",
            "address_1926", "lat_1926", "lon_1926",
            "address_2019", "lat_2019", "lon_2019",
        ]

        info_2019 = {}
        for dl in DataLayer.objects.filter(source="dc-churches-2019"):
            info_2019[dl.title] = {
                "address": (dl.data or {}).get("address", ""),
                "religion": (dl.data or {}).get("religion", ""),
                "lat": dl.lat,
                "lon": dl.lon,
            }

        rows = []
        for dl in DataLayer.objects.filter(source="dc-churches").select_related(
            "census_schedule__schedule_denomination"
        ).order_by("title"):
            data = dl.data or {}
            denom = ""
            family = ""
            rid = ""
            if dl.census_schedule_id:
                rid = dl.census_schedule.resource_id
                if dl.census_schedule.schedule_denomination:
                    denom = dl.census_schedule.schedule_denomination.name
                    family = dl.census_schedule.schedule_denomination.family_relec or ""
            if not denom:
                denom = data.get("denomination_override", "")
                family = data.get("denomination_family_override", "")

            matched_title = data.get("matched_2019_title", "")
            i = info_2019.get(matched_title, {})

            rows.append({
                "church_name_1926": dl.title,
                "resource_id": rid,
                "church_name_2019": matched_title,
                "match_method": data.get("match_method", ""),
                "denomination_1926": denom,
                "denomination_family": family,
                "religion_2019": i.get("religion", ""),
                "address_1926": data.get("address", ""),
                "lat_1926": dl.lat,
                "lon_1926": dl.lon,
                "address_2019": i.get("address", ""),
                "lat_2019": i.get("lat", ""),
                "lon_2019": i.get("lon", ""),
            })

        # Add 2019-only
        matched_2019_titles = {r["church_name_2019"] for r in rows if r["church_name_2019"]}
        for dl in DataLayer.objects.filter(source="dc-churches-2019").order_by("title"):
            if dl.title not in matched_2019_titles:
                rows.append({
                    "church_name_1926": "",
                    "resource_id": "",
                    "church_name_2019": dl.title,
                    "match_method": "",
                    "denomination_1926": "",
                    "denomination_family": "",
                    "religion_2019": (dl.data or {}).get("religion", ""),
                    "address_1926": "",
                    "lat_1926": "",
                    "lon_1926": "",
                    "address_2019": (dl.data or {}).get("address", ""),
                    "lat_2019": dl.lat,
                    "lon_2019": dl.lon,
                })

        path = STATIC_DATA / "dc-churches-matched.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=match_fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        matched = sum(1 for r in rows if r["church_name_1926"] and r["church_name_2019"])
        self.stdout.write(self.style.SUCCESS(
            f"  dc-churches-matched.csv: {len(rows)} rows ({matched} matched)"
        ))
