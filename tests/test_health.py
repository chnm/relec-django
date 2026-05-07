import pytest
from unittest.mock import patch


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["code"] == 200

    def test_health_returns_503_when_db_unavailable(self, client):
        with patch(
            "religious_ecologies.middleware.connection.ensure_connection",
            side_effect=Exception("connection refused"),
        ):
            response = client.get("/health/")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["code"] == 503
            assert "database unavailable" in data["detail"]

    def test_health_does_not_interfere_with_other_routes(self, client):
        response = client.get("/nonexistent-page/")
        assert response.status_code != 503
