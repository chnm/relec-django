import pytest
from django.urls import reverse

from pages.models import Page


@pytest.mark.django_db
def test_ai_statement_page_is_seeded_and_in_nav(client):
    page = Page.objects.get(slug="ai-statement")
    assert page.show_in_nav and page.is_live

    response = client.get(reverse("page_detail", kwargs={"slug": "ai-statement"}))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Our Use of AI" in content
    assert "Every transcription is reviewed by a person" in content
    assert 'href="/ai-statement/"' in content
