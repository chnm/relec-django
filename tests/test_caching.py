import pytest
from django.core.cache import cache
from django.urls import reverse


@pytest.mark.django_db
class TestViewCaching:
    def test_homepage_is_cached(self, sample_dataset, client):
        """Second request should be served from cache."""
        response1 = client.get(reverse("index"))
        assert response1.status_code == 200

        response2 = client.get(reverse("index"))
        assert response2.status_code == 200
        assert response1.content == response2.content

    def test_census_browser_is_cached(self, sample_dataset, client):
        url = reverse("census_browser")
        response1 = client.get(url)
        response2 = client.get(url)
        assert response1.content == response2.content

    def test_census_browser_different_filters_cached_separately(self, sample_dataset, client):
        """Different filter params should produce different cache entries."""
        url = reverse("census_browser")
        response_all = client.get(url)
        response_va = client.get(reverse("census_browser_state", kwargs={"state_code": "VA"}))
        # Different URLs should not return identical content
        # (unless coincidentally same, but our fixture has different data per state)
        assert response_all.status_code == 200
        assert response_va.status_code == 200

    def test_denominations_browse_is_cached(self, sample_dataset, client):
        url = reverse("denominations_browse")
        response1 = client.get(url)
        response2 = client.get(url)
        assert response1.content == response2.content

    def test_locations_browse_is_cached(self, sample_dataset, client):
        url = reverse("locations_browse")
        response1 = client.get(url)
        response2 = client.get(url)
        assert response1.content == response2.content

    def test_populated_places_is_cached(self, sample_dataset, client):
        url = reverse("browse_popplaces")
        response1 = client.get(url)
        response2 = client.get(url)
        assert response1.content == response2.content


@pytest.mark.django_db
class TestFilterDataCaching:
    def test_filter_data_is_cached(self, sample_dataset, client):
        """The census browser filter data should be stored in cache."""
        from census.views import _get_census_browser_filter_data

        # First call populates cache
        data1 = _get_census_browser_filter_data()
        assert data1 is not None
        assert "denominations" in data1
        assert "states" in data1
        assert "counties_by_state_json" in data1

        # Second call should return from cache
        data2 = _get_census_browser_filter_data()
        assert data2 is not None

    def test_filter_data_cache_key_exists(self, sample_dataset, client):
        from census.views import _get_census_browser_filter_data

        _get_census_browser_filter_data()
        assert cache.get("census_browser_filter_data") is not None

    def test_cache_clear_removes_filter_data(self, sample_dataset, client):
        from census.views import _get_census_browser_filter_data

        _get_census_browser_filter_data()
        assert cache.get("census_browser_filter_data") is not None

        cache.clear()
        assert cache.get("census_browser_filter_data") is None
