import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestHomepage:
    def test_homepage_returns_200(self, sample_dataset, client):
        response = client.get(reverse("index"))
        assert response.status_code == 200

    def test_homepage_contains_schedule_count(self, sample_dataset, client):
        response = client.get(reverse("index"))
        content = response.content.decode()
        # The page should show the total number of schedules somewhere
        assert str(len(sample_dataset["schedules"])) in content

    def test_homepage_contains_denomination_names(self, sample_dataset, client):
        response = client.get(reverse("index"))
        content = response.content.decode()
        assert "Methodist" in content


@pytest.mark.django_db
class TestCensusBrowser:
    def test_browser_returns_200(self, sample_dataset, client):
        response = client.get(reverse("census_browser"))
        assert response.status_code == 200

    def test_browser_contains_filter_dropdowns(self, sample_dataset, client):
        response = client.get(reverse("census_browser"))
        content = response.content.decode()
        # The page should contain state and denomination data for dropdowns
        assert "Virginia" in content
        assert "Methodist" in content

    def test_browser_filter_by_state(self, sample_dataset, client):
        response = client.get(
            reverse("census_browser_state", kwargs={"state_code": "VA"})
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Virginia" in content

    def test_browser_filter_by_state_and_county(self, sample_dataset, client):
        response = client.get(
            reverse(
                "census_browser_county",
                kwargs={"state_code": "NJ", "county_name": "Cape May"},
            )
        )
        assert response.status_code == 200

    def test_browser_filter_by_denomination(self, sample_dataset, client):
        denom = sample_dataset["denominations"][0]
        response = client.get(
            reverse("census_browser"), {"denomination": denom.id}
        )
        assert response.status_code == 200

    def test_browser_search(self, sample_dataset, client):
        response = client.get(
            reverse("census_browser"), {"search": "Methodist"}
        )
        assert response.status_code == 200

    def test_browser_pagination(self, sample_dataset, client):
        response = client.get(reverse("census_browser"))
        assert response.status_code == 200
        content = response.content.decode()
        # Should show record count somewhere
        assert str(len(sample_dataset["schedules"])) in content

    def test_browser_empty_results(self, client):
        response = client.get(
            reverse("census_browser"), {"search": "nonexistent_xyz"}
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestCensusDetail:
    def test_detail_returns_200(self, census_schedule, client):
        response = client.get(
            reverse("census_detail", kwargs={"resource_id": census_schedule.resource_id})
        )
        assert response.status_code == 200

    def test_detail_404_for_missing_record(self, client):
        response = client.get(
            reverse("census_detail", kwargs={"resource_id": 99999})
        )
        assert response.status_code == 404

    def test_detail_contains_schedule_title(self, census_schedule, client):
        response = client.get(
            reverse("census_detail", kwargs={"resource_id": census_schedule.resource_id})
        )
        content = response.content.decode()
        assert census_schedule.schedule_title in content


@pytest.mark.django_db
class TestDenominationsBrowse:
    def test_returns_200(self, sample_dataset, client):
        response = client.get(reverse("denominations_browse"))
        assert response.status_code == 200

    def test_contains_denomination_names(self, sample_dataset, client):
        response = client.get(reverse("denominations_browse"))
        content = response.content.decode()
        assert "Methodist" in content
        assert "Baptist" in content


@pytest.mark.django_db
class TestLocationsBrowse:
    def test_returns_200(self, sample_dataset, client):
        response = client.get(reverse("locations_browse"))
        assert response.status_code == 200

    def test_contains_state_names(self, sample_dataset, client):
        response = client.get(reverse("locations_browse"))
        content = response.content.decode()
        assert "Virginia" in content
        assert "New Jersey" in content


@pytest.mark.django_db
class TestPopulatedPlacesBrowse:
    def test_returns_200(self, sample_dataset, client):
        response = client.get(reverse("browse_popplaces"))
        assert response.status_code == 200

    def test_contains_place_names(self, sample_dataset, client):
        response = client.get(reverse("browse_popplaces"))
        content = response.content.decode()
        assert "Falls Church" in content
        assert "Cape May City" in content
