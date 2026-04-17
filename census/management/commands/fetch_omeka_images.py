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

from census.models import CensusSchedule


class Command(BaseCommand):
    help = "Fetch and store images from Omeka API for CensusSchedule records"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_logging()

    def setup_logging(self):
        """Set up logging for the command"""
        logs_dir = Path(settings.BASE_DIR) / "logs"
        logs_dir.mkdir(exist_ok=True)

        log_filename = (
            f"fetch_omeka_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
            help="Limit number of records to process (for testing)",
        )
        parser.add_argument(
            "--test", action="store_true", help="Test mode: process only 5-10 records"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry run: show what would be processed without downloading",
        )
        parser.add_argument(
            "--force", action="store_true", help="Force re-download of existing images"
        )
        parser.add_argument(
            "--start-from",
            type=int,
            default=None,
            help="Start processing from specific record ID (for resuming)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Delay in seconds between API requests (default: 0.5)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Process records in batches (default: 100)",
        )

    def handle(self, *args, **options):
        """Main command handler"""
        limit = options.get("limit")
        test_mode = options.get("test")
        dry_run = options.get("dry_run")
        force = options.get("force")
        start_from = options.get("start_from")
        delay = options.get("delay")
        batch_size = options.get("batch_size")

        if test_mode:
            limit = 10
            self.stdout.write(
                self.style.WARNING(
                    f"Running in TEST MODE - processing max {limit} records"
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Running in DRY RUN MODE - no images will be downloaded"
                )
            )

        self.stdout.write(f"Using delay of {delay}s between requests")

        # Get all CensusSchedule records (using resource_id as Omeka item ID)
        queryset = CensusSchedule.objects.all().order_by("id")

        if start_from:
            queryset = queryset.filter(id__gte=start_from)
            self.stdout.write(f"Starting from record ID {start_from}")

        if limit:
            queryset = queryset[:limit]

        total_records = queryset.count()
        self.stdout.write(f"Found {total_records} records to process")
        self.logger.info(
            f"Starting image fetch for {total_records} records with {delay}s delay"
        )

        processed = 0
        downloaded = 0
        skipped = 0
        errors = 0

        # Process in batches to handle large datasets
        batch_start = 0
        while batch_start < total_records:
            batch_end = min(batch_start + batch_size, total_records)
            batch_queryset = queryset[batch_start:batch_end]

            self.stdout.write(
                f"\nProcessing batch {batch_start + 1}-{batch_end} of {total_records}"
            )

            for schedule in batch_queryset:
                try:
                    result = self.process_schedule(
                        schedule, dry_run=dry_run, force=force, delay=delay
                    )
                    processed += 1

                    if result == "downloaded":
                        downloaded += 1
                    elif result == "skipped":
                        skipped += 1

                    if processed % 10 == 0:
                        self.stdout.write(
                            f"Processed {processed}/{total_records} records... (last: ID {schedule.id})"
                        )

                except KeyboardInterrupt:
                    self.stdout.write(
                        self.style.ERROR(
                            f"\nInterrupted! Last processed: Schedule ID {schedule.id}"
                        )
                    )
                    self.stdout.write(f"To resume, use: --start-from {schedule.id + 1}")
                    break
                except Exception as e:
                    errors += 1
                    self.logger.error(
                        f"Error processing schedule {schedule.id}: {str(e)}"
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing schedule {schedule.id}: {str(e)}"
                        )
                    )
                    # Continue processing despite errors

            batch_start += batch_size

            # Small pause between batches
            if batch_start < total_records:
                time.sleep(1)

        # Final summary
        self.stdout.write(self.style.SUCCESS("\nSummary:"))
        self.stdout.write(f"  Total processed: {processed}")
        self.stdout.write(f"  Images downloaded: {downloaded}")
        self.stdout.write(f"  Skipped: {skipped}")
        self.stdout.write(f"  Errors: {errors}")

        self.logger.info(
            f"Command completed. Processed: {processed}, Downloaded: {downloaded}, Skipped: {skipped}, Errors: {errors}"
        )

    def process_schedule(self, schedule, dry_run=False, force=False, delay=0.5):
        """Process a single CensusSchedule record"""
        omeka_item_id = schedule.resource_id

        # Skip records without resource IDs (this should be rare since resource_id is required)
        if not omeka_item_id:
            self.logger.info(
                f"Schedule {schedule.id} has no resource ID - skipping (needs manual review)"
            )
            return "skipped"

        # Rate limiting - delay between requests
        if delay > 0:
            time.sleep(delay)

        # Check if we already have an image (unless forcing)
        if schedule.original_image and not force:
            self.logger.info(f"Schedule {schedule.id} already has image, skipping")
            return "skipped"

        # Fetch item data from Omeka API
        item_data = self.fetch_omeka_item(omeka_item_id)
        if not item_data:
            self.logger.error(
                f"Could not fetch item data for resource ID {omeka_item_id}"
            )
            return "error"

        # Get media IDs from item
        media_ids = self.extract_media_ids(item_data)
        if not media_ids:
            self.logger.warning(
                f"No media found for Omeka item with resource ID {omeka_item_id}"
            )
            return "skipped"

        # Process the first media item (assuming one image per item)
        media_id = media_ids[0]
        media_data = self.fetch_omeka_media(media_id)

        if not media_data:
            self.logger.error(f"Could not fetch media data for media ID {media_id}")
            return "error"

        # Get image URL
        image_url = media_data.get("o:original_url")
        if not image_url:
            self.logger.error(f"No original URL found for media ID {media_id}")
            return "error"

        if dry_run:
            self.stdout.write(f"Would download: {image_url} for schedule {schedule.id}")
            return "skipped"

        # Download and save image
        success = self.download_and_save_image(schedule, image_url, media_id)
        return "downloaded" if success else "error"

    def fetch_omeka_item(self, item_id, max_retries=3):
        """Fetch item data from Omeka API with retry logic"""
        url = f"https://omeka.religiousecologies.org/api/items/{item_id}"

        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                return response.json()
            except requests.Timeout:
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff
                    self.logger.warning(
                        f"Timeout fetching item {item_id}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Timeout fetching item {item_id} after {max_retries + 1} attempts"
                    )
            except requests.RequestException as e:
                if attempt < max_retries:
                    wait_time = 2**attempt
                    self.logger.warning(
                        f"Error fetching item {item_id}: {str(e)}, retrying in {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Error fetching item {item_id} after {max_retries + 1} attempts: {str(e)}"
                    )
        return None

    def fetch_omeka_media(self, media_id, max_retries=3):
        """Fetch media data from Omeka API with retry logic"""
        url = f"https://omeka.religiousecologies.org/api/media/{media_id}"

        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                return response.json()
            except requests.Timeout:
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff
                    self.logger.warning(
                        f"Timeout fetching media {media_id}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Timeout fetching media {media_id} after {max_retries + 1} attempts"
                    )
            except requests.RequestException as e:
                if attempt < max_retries:
                    wait_time = 2**attempt
                    self.logger.warning(
                        f"Error fetching media {media_id}: {str(e)}, retrying in {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Error fetching media {media_id} after {max_retries + 1} attempts: {str(e)}"
                    )
        return None

    def extract_media_ids(self, item_data):
        """Extract media IDs from item data"""
        media_list = item_data.get("o:media", [])
        return [media["o:id"] for media in media_list]

    def download_and_save_image(self, schedule, image_url, media_id, max_retries=3):
        """Download image and save to schedule with retry logic"""
        for attempt in range(max_retries + 1):
            try:
                # Download image
                response = requests.get(
                    image_url, timeout=120
                )  # Longer timeout for large images
                response.raise_for_status()
                break
            except requests.Timeout:
                if attempt < max_retries:
                    wait_time = 2**attempt
                    self.logger.warning(
                        f"Timeout downloading image for schedule {schedule.id}, retrying in {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Timeout downloading image for schedule {schedule.id} after {max_retries + 1} attempts"
                    )
                    return False
            except requests.RequestException as e:
                if attempt < max_retries:
                    wait_time = 2**attempt
                    self.logger.warning(
                        f"Error downloading image for schedule {schedule.id}: {str(e)}, retrying in {wait_time}s"
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Error downloading image for schedule {schedule.id} after {max_retries + 1} attempts: {str(e)}"
                    )
                    return False

        try:
            # Get file extension from URL
            parsed_url = urlparse(image_url)
            filename = os.path.basename(parsed_url.path)
            if not filename or "." not in filename:
                filename = f"omeka_media_{media_id}.jpg"

            # Generate unique filename
            base_name, ext = os.path.splitext(filename)
            unique_filename = f"schedule_{schedule.id}_{base_name}_{media_id}{ext}"

            # Create Django File object from content
            image_content = ContentFile(response.content, name=unique_filename)

            # Update schedule record with the image
            with transaction.atomic():
                # Save image to the ImageField and update path in one operation
                schedule.original_image.save(unique_filename, image_content, save=False)
                schedule.datascribe_original_image_path = schedule.original_image.name
                schedule.save(
                    update_fields=["original_image", "datascribe_original_image_path"]
                )

            self.logger.info(
                f"Downloaded image for schedule {schedule.id}: {schedule.original_image.name}"
            )
            self.stdout.write(
                f"  Downloaded: {unique_filename} for schedule {schedule.id}"
            )

            return True

        except Exception as e:
            self.logger.error(
                f"Error saving image for schedule {schedule.id}: {str(e)}"
            )
            return False
