import pytest
from django.core.cache import cache
from django.core.management import call_command


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
