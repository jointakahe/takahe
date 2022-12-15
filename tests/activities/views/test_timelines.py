import pytest


@pytest.mark.django_db
def test_content_warning_text(client_with_identity, config_system):

    config_system.content_warning_text = "Content Summary"

    response = client_with_identity.get("/")

    assert response.status_code == 200
    assert 'placeholder="Content Summary"' in str(response.rendered_content)
