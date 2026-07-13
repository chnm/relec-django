import pytest
from django.core.cache import cache
from django.core.management import call_command

from census.management.commands.import_datascribe_data import map_workflow_status


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
