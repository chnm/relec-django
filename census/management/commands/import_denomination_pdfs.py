import logging
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from census.models import Denomination, DenominationCensusReport

OMEKA_BASE_URL = "https://omeka.religiousecologies.org/api"
DENOMINATIONS_ITEM_SET_ID = 3330


class Command(BaseCommand):
    help = "Import denomination census report PDFs from Omeka (item set 3330)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_logging()

    def setup_logging(self):
        logs_dir = Path(settings.BASE_DIR) / "logs"
        logs_dir.mkdir(exist_ok=True)

        log_filename = (
            f"import_denomination_pdfs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        log_path = logs_dir / log_filename

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of Omeka items to process (for testing)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be downloaded without actually downloading",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download PDFs even if omeka_media_id already exists",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Delay in seconds between API requests (default: 0.5)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]
        limit = options["limit"]
        delay = options["delay"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN — no files will be downloaded")
            )

        # Build denomination lookup by denomination_id
        denom_lookup = {}
        for d in Denomination.objects.all():
            if d.denomination_id:
                denom_lookup[d.denomination_id] = d

        self.stdout.write(f"Loaded {len(denom_lookup)} denominations for matching")

        # Paginate through Omeka items in set 3330
        page = 1
        per_page = 25
        items_processed = 0
        pdfs_downloaded = 0
        pdfs_skipped = 0
        denom_not_found = 0
        errors = 0

        while True:
            if limit and items_processed >= limit:
                break

            url = (
                f"{OMEKA_BASE_URL}/items"
                f"?item_set_id={DENOMINATIONS_ITEM_SET_ID}"
                f"&per_page={per_page}&page={page}"
            )
            self.logger.info(f"Fetching page {page}: {url}")

            items = self._fetch_json(url)
            if items is None:
                self.stdout.write(self.style.ERROR(f"Failed to fetch page {page}"))
                break

            if not items:
                # Empty page — we've reached the end
                break

            for item in items:
                if limit and items_processed >= limit:
                    break

                items_processed += 1
                result = self._process_item(
                    item, denom_lookup, dry_run=dry_run, force=force, delay=delay
                )

                if result == "downloaded":
                    pdfs_downloaded += 1
                elif result == "skipped":
                    pdfs_skipped += 1
                elif result == "no_denom":
                    denom_not_found += 1
                elif result == "error":
                    errors += 1

            page += 1
            if delay > 0:
                time.sleep(delay)

        # Summary
        self.stdout.write(self.style.SUCCESS("\nSummary:"))
        self.stdout.write(f"  Items processed:        {items_processed}")
        self.stdout.write(f"  PDFs downloaded:        {pdfs_downloaded}")
        self.stdout.write(f"  Skipped (existing):     {pdfs_skipped}")
        self.stdout.write(f"  Denomination not found: {denom_not_found}")
        self.stdout.write(f"  Errors:                 {errors}")

    def _process_item(self, item, denom_lookup, dry_run=False, force=False, delay=0.5):
        """Process a single Omeka item: match denomination, find PDF media, download."""
        item_id = item.get("o:id")

        # Extract mare:denominationId from item values
        denom_id_value = self._extract_property(item, "mare:denominationId")
        if not denom_id_value:
            self.logger.warning(
                f"Item {item_id}: no mare:denominationId found, skipping"
            )
            return "no_denom"

        denomination = denom_lookup.get(denom_id_value)
        if not denomination:
            self.logger.warning(
                f"Item {item_id}: denomination_id '{denom_id_value}' not found in Django"
            )
            return "no_denom"

        # Get media list from item
        media_refs = item.get("o:media", [])
        if not media_refs:
            self.logger.info(f"Item {item_id}: no media attached")
            return "skipped"

        result = "skipped"
        for media_ref in media_refs:
            media_id = media_ref.get("o:id")
            if not media_id:
                continue

            # Check if we already have this media
            if not force and DenominationCensusReport.objects.filter(
                omeka_media_id=media_id
            ).exists():
                self.logger.info(f"Media {media_id}: already imported, skipping")
                continue

            if delay > 0:
                time.sleep(delay)

            # Fetch media detail to get type and URL
            media_data = self._fetch_json(f"{OMEKA_BASE_URL}/media/{media_id}")
            if not media_data:
                self.logger.error(f"Media {media_id}: failed to fetch details")
                result = "error"
                continue

            media_type = media_data.get("o:media_type", "")
            if media_type != "application/pdf":
                self.logger.info(
                    f"Media {media_id}: type is '{media_type}', not PDF — skipping"
                )
                continue

            original_url = media_data.get("o:original_url")
            if not original_url:
                self.logger.error(f"Media {media_id}: no o:original_url")
                result = "error"
                continue

            title = media_data.get("o:source", "") or media_data.get("dcterms:title", "")
            # dcterms:title may be a list of dicts
            if isinstance(title, list) and title:
                title = title[0].get("@value", "") if isinstance(title[0], dict) else str(title[0])

            # Derive filename
            parsed = urlparse(original_url)
            original_filename = os.path.basename(parsed.path) or f"media_{media_id}.pdf"

            if dry_run:
                self.stdout.write(
                    f"  Would download: {original_url}\n"
                    f"    → denomination: {denomination.name} ({denom_id_value})\n"
                    f"    → media_id: {media_id}, title: {title or original_filename}"
                )
                result = "downloaded"
                continue

            # Download PDF
            success = self._download_pdf(
                denomination=denomination,
                item_id=item_id,
                media_id=media_id,
                title=title,
                original_filename=original_filename,
                url=original_url,
                force=force,
            )

            if success:
                result = "downloaded"
            else:
                result = "error"

        return result

    def _download_pdf(
        self, denomination, item_id, media_id, title, original_filename, url, force=False
    ):
        """Download a PDF and create/update DenominationCensusReport."""
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            self.logger.error(f"Failed to download {url}: {e}")
            return False

        try:
            # Build a clean filename
            safe_name = f"denom_{denomination.denomination_id}_{media_id}.pdf"
            content = ContentFile(response.content, name=safe_name)

            with transaction.atomic():
                if force:
                    # Delete existing if forcing re-download
                    DenominationCensusReport.objects.filter(
                        omeka_media_id=media_id
                    ).delete()

                report = DenominationCensusReport(
                    denomination=denomination,
                    title=title or original_filename,
                    original_filename=original_filename,
                    omeka_item_id=item_id,
                    omeka_media_id=media_id,
                )
                report.pdf_file.save(safe_name, content, save=False)
                report.save()

            self.stdout.write(
                f"  Downloaded: {safe_name} for {denomination.name}"
            )
            self.logger.info(
                f"Saved PDF media_id={media_id} for denomination {denomination.name}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error saving PDF media_id={media_id}: {e}")
            return False

    def _extract_property(self, item, property_term):
        """Extract a single value for a given JSON-LD property term from an Omeka item."""
        values = item.get(property_term, [])
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                return first.get("@value", "")
            return str(first)
        return None

    def _fetch_json(self, url, max_retries=3):
        """Fetch JSON from URL with retry logic."""
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                return response.json()
            except requests.Timeout:
                if attempt < max_retries:
                    wait = 2**attempt
                    self.logger.warning(
                        f"Timeout fetching {url}, retrying in {wait}s "
                        f"(attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(wait)
                else:
                    self.logger.error(
                        f"Timeout fetching {url} after {max_retries + 1} attempts"
                    )
            except requests.RequestException as e:
                if attempt < max_retries:
                    wait = 2**attempt
                    self.logger.warning(
                        f"Error fetching {url}: {e}, retrying in {wait}s"
                    )
                    time.sleep(wait)
                else:
                    self.logger.error(
                        f"Error fetching {url} after {max_retries + 1} attempts: {e}"
                    )
        return None
