import csv
from io import StringIO
from unittest.mock import Mock, patch

import pytest
import requests
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from census.management.commands.import_datascribe_data import map_workflow_status
from census.transcription.worker import ClaudeTranscriptionWorker

from .factories import CensusScheduleFactory


@pytest.mark.django_db
class TestClearCacheCommand:
    def test_clears_cache(self):
        cache.set("test_key", "test_value", 300)
        assert cache.get("test_key") == "test_value"

        call_command("clear_cache")

        assert cache.get("test_key") is None

    def test_outputs_success_message(self, capsys):
        call_command("clear_cache")
        captured = capsys.readouterr()
        assert "Cache cleared successfully" in captured.out


@pytest.mark.parametrize(
    ("reviewed", "is_approved", "expected"),
    [
        ("1", "1", "approved"),
        ("1", "0", "needs_review"),
        ("0", "0", "needs_review"),
        (None, None, "needs_review"),
    ],
)
def test_imported_workflow_status_defaults_to_review(
    reviewed, is_approved, expected
):
    assert map_workflow_status(reviewed, is_approved) == expected


def write_image_manifest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as manifest_file:
        writer = csv.writer(manifest_file)
        writer.writerow(["resource_id", "original_image"])
        writer.writerows(rows)


@pytest.mark.django_db
class TestScheduleImageManifestCommands:
    def test_export_writes_only_linked_images_in_resource_order(self, tmp_path):
        CensusScheduleFactory(resource_id=300, original_image="")
        CensusScheduleFactory(
            resource_id=200,
            original_image="census_images/originals/two.jpg",
        )
        CensusScheduleFactory(
            resource_id=100,
            original_image="census_images/originals/one.jpg",
        )
        output = tmp_path / "images.csv"
        stdout = StringIO()

        call_command("export_schedule_image_manifest", output, stdout=stdout)

        with output.open("r", encoding="utf-8", newline="") as manifest_file:
            assert list(csv.reader(manifest_file)) == [
                ["resource_id", "original_image"],
                ["100", "census_images/originals/one.jpg"],
                ["200", "census_images/originals/two.jpg"],
            ]
        assert "Exported 2 schedule image mappings" in stdout.getvalue()

    def test_export_refuses_to_overwrite_existing_file(self, tmp_path):
        output = tmp_path / "images.csv"
        output.write_text("keep me", encoding="utf-8")

        with pytest.raises(CommandError, match="already exists"):
            call_command("export_schedule_image_manifest", output)

        assert output.read_text(encoding="utf-8") == "keep me"

    def test_import_links_existing_object_key_by_resource_id(self, tmp_path):
        schedule = CensusScheduleFactory(resource_id=6893)
        manifest = tmp_path / "images.csv"
        object_key = "census_images/originals/schedule_19_scan_6913.jpg"
        write_image_manifest(manifest, [[schedule.resource_id, object_key]])

        call_command("import_schedule_image_manifest", manifest)

        schedule.refresh_from_db()
        assert schedule.original_image.name == object_key

    def test_import_dry_run_verifies_storage_without_linking(self, tmp_path):
        schedule = CensusScheduleFactory(resource_id=6893)
        manifest = tmp_path / "images.csv"
        object_key = "census_images/originals/schedule_19_scan_6913.jpg"
        write_image_manifest(manifest, [[schedule.resource_id, object_key]])
        stdout = StringIO()

        with patch(
            "census.management.commands.import_schedule_image_manifest."
            "default_storage.exists",
            return_value=True,
        ) as exists:
            call_command(
                "import_schedule_image_manifest",
                manifest,
                dry_run=True,
                verify_storage=True,
                stdout=stdout,
            )

        schedule.refresh_from_db()
        assert not schedule.original_image
        exists.assert_called_once_with(object_key)
        assert "Images that would be linked: 1" in stdout.getvalue()
        assert "Verified storage objects: 1" in stdout.getvalue()

    def test_import_limit_bounds_manifest_rows(self, tmp_path):
        first = CensusScheduleFactory(resource_id=100)
        second = CensusScheduleFactory(resource_id=200)
        manifest = tmp_path / "images.csv"
        write_image_manifest(
            manifest,
            [
                [first.resource_id, "census_images/originals/first.jpg"],
                [second.resource_id, "census_images/originals/second.jpg"],
            ],
        )

        call_command("import_schedule_image_manifest", manifest, limit=1)

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.original_image.name == "census_images/originals/first.jpg"
        assert not second.original_image

    def test_import_is_idempotent_and_refuses_conflicts(self, tmp_path):
        object_key = "census_images/originals/existing.jpg"
        schedule = CensusScheduleFactory(resource_id=100, original_image=object_key)
        matching_manifest = tmp_path / "matching.csv"
        write_image_manifest(
            matching_manifest,
            [[schedule.resource_id, object_key]],
        )
        stdout = StringIO()

        call_command(
            "import_schedule_image_manifest",
            matching_manifest,
            stdout=stdout,
        )

        assert "Already linked: 1" in stdout.getvalue()

        conflicting_manifest = tmp_path / "conflicting.csv"
        write_image_manifest(
            conflicting_manifest,
            [[schedule.resource_id, "census_images/originals/different.jpg"]],
        )
        with pytest.raises(CommandError, match="blocking error"):
            call_command("import_schedule_image_manifest", conflicting_manifest)

        schedule.refresh_from_db()
        assert schedule.original_image.name == object_key

    @pytest.mark.parametrize(
        "object_key",
        [
            "https://obj.example.org/bucket/image.jpg",
            "../census_images/originals/image.jpg",
            "legacy/path/image.jpg",
            "census_images/originals/",
        ],
    )
    def test_import_rejects_invalid_object_keys(
        self,
        tmp_path,
        object_key,
    ):
        schedule = CensusScheduleFactory(resource_id=100)
        manifest = tmp_path / "invalid.csv"
        write_image_manifest(manifest, [[schedule.resource_id, object_key]])

        with pytest.raises(CommandError, match="blocking error"):
            call_command("import_schedule_image_manifest", manifest)

        schedule.refresh_from_db()
        assert not schedule.original_image

    def test_import_reports_missing_storage_object_as_blocking(self, tmp_path):
        schedule = CensusScheduleFactory(resource_id=100)
        manifest = tmp_path / "missing.csv"
        object_key = "census_images/originals/missing.jpg"
        write_image_manifest(manifest, [[schedule.resource_id, object_key]])

        with patch(
            "census.management.commands.import_schedule_image_manifest."
            "default_storage.exists",
            return_value=False,
        ):
            with pytest.raises(CommandError, match="blocking error"):
                call_command(
                    "import_schedule_image_manifest",
                    manifest,
                    verify_storage=True,
                )

        schedule.refresh_from_db()
        assert not schedule.original_image


def api_image_result(resource_id, object_key=None):
    image_url = None
    if object_key is not None:
        image_url = (
            "https://obj.rrchnm.org/database.religiousecologies.org/"
            f"{object_key}?AWSAccessKeyId=public-signed-value&Signature=discard"
        )
    return {
        "urls": {
            "self": f"http://religiousecologies.org/census/record/{resource_id}/",
            "image": image_url,
        }
    }


def mock_api_response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class TestFetchScheduleImageManifestCommand:
    def test_fetch_writes_unsigned_object_keys_and_skips_missing_images(
        self,
        tmp_path,
    ):
        output = tmp_path / "api-images.csv"
        object_key = "census_images/originals/schedule_19_scan_6913.jpg"
        payload = {
            "next": None,
            "results": [
                api_image_result(6893, object_key),
                api_image_result(7000),
            ],
        }
        session = Mock()
        session.get.return_value = mock_api_response(payload)

        with patch(
            "census.management.commands.fetch_schedule_image_manifest."
            "requests.Session",
            return_value=session,
        ):
            call_command("fetch_schedule_image_manifest", output, delay=0)

        with output.open("r", encoding="utf-8", newline="") as manifest_file:
            assert list(csv.reader(manifest_file)) == [
                ["resource_id", "original_image"],
                ["6893", object_key],
            ]
        request_kwargs = session.get.call_args.kwargs
        assert request_kwargs["params"] == {
            "page": 1,
            "page_size": 100,
            "view": "map",
        }
        assert "AWSAccessKeyId" not in output.read_text(encoding="utf-8")
        session.close.assert_called_once()

    def test_fetch_uses_numbered_https_requests_instead_of_next_url(
        self,
        tmp_path,
    ):
        output = tmp_path / "api-images.csv"
        first_key = "census_images/originals/first.jpg"
        second_key = "census_images/originals/second.jpg"
        first_page = {
            "next": "http://religiousecologies.org/census/api/"
            "religious-bodies/?page=2",
            "results": [api_image_result(100, first_key)],
        }
        second_page = {
            "next": None,
            "results": [api_image_result(200, second_key)],
        }
        session = Mock()
        session.get.side_effect = [
            mock_api_response(first_page),
            mock_api_response(second_page),
        ]

        with patch(
            "census.management.commands.fetch_schedule_image_manifest."
            "requests.Session",
            return_value=session,
        ):
            call_command(
                "fetch_schedule_image_manifest",
                output,
                limit=2,
                page_size=10,
                delay=0,
            )

        assert session.get.call_count == 2
        assert session.get.call_args_list[0].args[0].startswith("https://")
        assert session.get.call_args_list[1].args[0].startswith("https://")
        assert session.get.call_args_list[0].kwargs["params"]["page"] == 1
        assert session.get.call_args_list[1].kwargs["params"]["page"] == 2
        with output.open("r", encoding="utf-8", newline="") as manifest_file:
            assert list(csv.reader(manifest_file))[1:] == [
                ["100", first_key],
                ["200", second_key],
            ]

    def test_fetch_retries_transient_request_failure(self, tmp_path):
        output = tmp_path / "api-images.csv"
        payload = {
            "next": None,
            "results": [
                api_image_result(100, "census_images/originals/first.jpg")
            ],
        }
        session = Mock()
        session.get.side_effect = [
            requests.Timeout("temporary"),
            mock_api_response(payload),
        ]

        with (
            patch(
                "census.management.commands.fetch_schedule_image_manifest."
                "requests.Session",
                return_value=session,
            ),
            patch(
                "census.management.commands.fetch_schedule_image_manifest.time.sleep"
            ) as sleep,
        ):
            call_command("fetch_schedule_image_manifest", output, delay=0)

        assert session.get.call_count == 2
        sleep.assert_called_once_with(1)

    def test_fetch_refuses_invalid_api_image_path(self, tmp_path):
        output = tmp_path / "api-images.csv"
        payload = {
            "next": None,
            "results": [
                {
                    "urls": {
                        "self": (
                            "https://religiousecologies.org/census/record/100/"
                        ),
                        "image": "https://obj.rrchnm.org/bucket/legacy/image.jpg",
                    }
                }
            ],
        }
        session = Mock()
        session.get.return_value = mock_api_response(payload)

        with patch(
            "census.management.commands.fetch_schedule_image_manifest."
            "requests.Session",
            return_value=session,
        ):
            with pytest.raises(CommandError, match="no recognized object key"):
                call_command("fetch_schedule_image_manifest", output, delay=0)

        assert not output.exists()

    def test_fetch_refuses_to_overwrite_existing_manifest(self, tmp_path):
        output = tmp_path / "api-images.csv"
        output.write_text("keep me", encoding="utf-8")

        with pytest.raises(CommandError, match="already exists"):
            call_command("fetch_schedule_image_manifest", output)

        assert output.read_text(encoding="utf-8") == "keep me"


@pytest.mark.django_db
class TestTranscriptionWorkerLiveness:
    """The container healthcheck reads the file these tests assert on."""

    @override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True, ANTHROPIC_API_KEY="test-key")
    def test_working_worker_refreshes_the_liveness_file(self, tmp_path):
        liveness = tmp_path / "alive"

        with patch.object(ClaudeTranscriptionWorker, "run_once", return_value=False):
            call_command(
                "run_transcription_worker",
                "--once",
                f"--liveness-file={liveness}",
            )

        assert liveness.exists()

    @override_settings(CLAUDE_TRANSCRIPTION_ENABLED=False, ANTHROPIC_API_KEY="")
    def test_disabled_worker_refreshes_it_before_idling(self, tmp_path):
        """A deliberately disabled worker must not look unhealthy."""
        liveness = tmp_path / "alive"

        with patch(
            "census.management.commands.run_transcription_worker.time.sleep"
        ) as sleep:
            sleep.side_effect = InterruptedError
            with pytest.raises(InterruptedError):
                call_command(
                    "run_transcription_worker",
                    "--idle-when-disabled",
                    f"--liveness-file={liveness}",
                )

        assert liveness.exists()

    @override_settings(CLAUDE_TRANSCRIPTION_ENABLED=True, ANTHROPIC_API_KEY="test-key")
    def test_liveness_file_can_be_disabled(self, tmp_path):
        liveness = tmp_path / "alive"

        with patch.object(ClaudeTranscriptionWorker, "run_once", return_value=False):
            call_command("run_transcription_worker", "--once", "--liveness-file=")

        assert not liveness.exists()
