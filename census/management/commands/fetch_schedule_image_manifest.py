import csv
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from django.core.management.base import BaseCommand, CommandError

from census.management.commands.import_schedule_image_manifest import (
    IMAGE_KEY_PREFIX,
    object_key_error,
)


DEFAULT_API_URL = (
    "https://religiousecologies.org/census/api/religious-bodies/"
)
RESOURCE_PATH_PATTERN = re.compile(r"/census/record/(?P<resource_id>\d+)/?$")
MAX_API_PAGE_SIZE = 5000


class Command(BaseCommand):
    help = (
        "Fetch schedule resource IDs and existing image object keys from the "
        "public Religious Ecologies API into a local CSV manifest"
    )

    def add_arguments(self, parser):
        parser.add_argument("output", type=Path, help="Destination CSV path")
        parser.add_argument(
            "--api-url",
            default=DEFAULT_API_URL,
            help=f"Religious bodies API URL (default: {DEFAULT_API_URL})",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after exporting this many unique image mappings",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=100,
            help="API records requested per page, maximum 5000 (default: 100)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Delay between successful page requests in seconds (default: 0.5)",
        )
        parser.add_argument(
            "--request-timeout",
            type=float,
            default=60,
            help="Timeout for each API request in seconds (default: 60)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace an existing destination file",
        )

    def handle(self, *args, **options):
        output = options["output"]
        api_url = options["api_url"]
        limit = options["limit"]
        page_size = options["page_size"]
        delay = options["delay"]
        request_timeout = options["request_timeout"]
        overwrite = options["overwrite"]

        self._validate_options(
            output=output,
            api_url=api_url,
            limit=limit,
            page_size=page_size,
            delay=delay,
            request_timeout=request_timeout,
            overwrite=overwrite,
        )

        session = requests.Session()
        session.headers.update(
            {"User-Agent": "ReligiousEcologiesLocalImageManifest/1.0"}
        )
        counts = Counter()
        seen = {}
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                writer = csv.writer(temporary_file)
                writer.writerow(["resource_id", "original_image"])

                page = 1
                while True:
                    requested_page_size = page_size
                    if limit is not None:
                        requested_page_size = min(
                            page_size,
                            max(1, limit - counts["exported"]),
                        )
                    payload = self._fetch_page(
                        session,
                        api_url,
                        page=page,
                        page_size=requested_page_size,
                        request_timeout=request_timeout,
                    )
                    counts["pages"] += 1

                    results = payload.get("results")
                    if not isinstance(results, list):
                        raise CommandError(
                            f"API page {page} has no valid results list."
                        )

                    for result in results:
                        counts["records"] += 1
                        mapping = self._extract_mapping(result, page=page)
                        if mapping is None:
                            counts["without_images"] += 1
                            continue
                        resource_id, object_key = mapping

                        previous_key = seen.get(resource_id)
                        if previous_key is not None:
                            if previous_key != object_key:
                                raise CommandError(
                                    f"API returned conflicting image keys for "
                                    f"resource_id {resource_id}."
                                )
                            counts["duplicates"] += 1
                            continue

                        seen[resource_id] = object_key
                        writer.writerow([resource_id, object_key])
                        counts["exported"] += 1
                        if limit is not None and counts["exported"] >= limit:
                            break

                    if limit is not None and counts["exported"] >= limit:
                        break
                    if not payload.get("next"):
                        break
                    if not results:
                        raise CommandError(
                            f"API page {page} was empty but advertised another page."
                        )

                    page += 1
                    if delay:
                        time.sleep(delay)

            os.replace(temporary_path, output)
            temporary_path = None
        finally:
            session.close()
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {counts['exported']} image mappings from "
                f"{counts['pages']} API page(s) into {output}."
            )
        )
        self.stdout.write(f"  API records examined: {counts['records']}")
        self.stdout.write(f"  Records without images: {counts['without_images']}")
        self.stdout.write(f"  Duplicate schedule mappings: {counts['duplicates']}")

    def _validate_options(
        self,
        *,
        output,
        api_url,
        limit,
        page_size,
        delay,
        request_timeout,
        overwrite,
    ):
        parsed_api_url = urlsplit(api_url)
        if parsed_api_url.scheme != "https" or not parsed_api_url.netloc:
            raise CommandError("--api-url must be an absolute HTTPS URL.")
        if limit is not None and limit < 1:
            raise CommandError("--limit must be at least 1.")
        if page_size < 1 or page_size > MAX_API_PAGE_SIZE:
            raise CommandError(
                f"--page-size must be between 1 and {MAX_API_PAGE_SIZE}."
            )
        if delay < 0:
            raise CommandError("--delay cannot be negative.")
        if request_timeout <= 0:
            raise CommandError("--request-timeout must be greater than zero.")
        if output.exists() and not overwrite:
            raise CommandError(
                f"Destination already exists: {output}. Use --overwrite to replace it."
            )
        if not output.parent.is_dir():
            raise CommandError(f"Destination directory does not exist: {output.parent}")

    def _fetch_page(
        self,
        session,
        api_url,
        *,
        page,
        page_size,
        request_timeout,
    ):
        params = {
            "page": page,
            "page_size": page_size,
            "view": "map",
        }
        for attempt in range(1, 5):
            try:
                response = session.get(
                    api_url,
                    params=params,
                    timeout=request_timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("API response is not a JSON object")
                return payload
            except (requests.RequestException, ValueError) as exc:
                if attempt == 4:
                    raise CommandError(
                        f"Could not fetch API page {page} after {attempt} attempts "
                        f"({type(exc).__name__})."
                    ) from exc
                time.sleep(2 ** (attempt - 1))
        raise AssertionError("unreachable")

    def _extract_mapping(self, result, *, page):
        if not isinstance(result, dict):
            raise CommandError(f"API page {page} contains a non-object result.")
        urls = result.get("urls")
        if not isinstance(urls, dict):
            raise CommandError(f"API page {page} contains a result without URLs.")

        image_url = urls.get("image")
        if not image_url:
            return None
        if not isinstance(image_url, str):
            raise CommandError(
                f"API page {page} contains a non-string image URL."
            )
        self_url = urls.get("self")
        if not isinstance(self_url, str):
            raise CommandError(
                f"API page {page} contains an imaged result without a self URL."
            )

        match = RESOURCE_PATH_PATTERN.search(urlsplit(self_url).path)
        if match is None:
            raise CommandError(
                f"API page {page} contains an unrecognized schedule self URL."
            )
        resource_id = int(match.group("resource_id"))

        parsed_image_url = urlsplit(image_url)
        if parsed_image_url.scheme != "https" or not parsed_image_url.netloc:
            raise CommandError(
                f"API page {page} contains a non-HTTPS image URL for "
                f"resource_id {resource_id}."
            )
        decoded_path = unquote(parsed_image_url.path)
        marker = f"/{IMAGE_KEY_PREFIX}"
        marker_index = decoded_path.find(marker)
        if marker_index < 0:
            raise CommandError(
                f"API page {page} image URL has no recognized object key for "
                f"resource_id {resource_id}."
            )
        object_key = decoded_path[marker_index + 1 :]
        error = object_key_error(object_key)
        if error:
            raise CommandError(
                f"API page {page} returned an invalid object key for "
                f"resource_id {resource_id}: {error}"
            )
        return resource_id, object_key
