import pytest
from django.urls import reverse

from pages.models import Page


@pytest.mark.django_db
def test_ai_statement_page_is_seeded_and_linked_from_footer_only(client):
    page = Page.objects.get(slug="ai-statement")
    assert page.is_live and not page.show_in_nav

    response = client.get(reverse("page_detail", kwargs={"slug": "ai-statement"}))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Our Use of AI" in content
    assert "Every transcription is reviewed by a person" in content
    # One link: the fixed footer entry, not the header/mobile nav loops.
    assert content.count('href="/ai-statement/"') == 1
