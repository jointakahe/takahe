import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from pytest_httpx import HTTPXMock

from stator.runner import StatorRunner
from users.models import Identity, InboxMessage
from users.services import IdentityService


@pytest.mark.django_db
def test_import_following(
    client_with_user: Client,
    identity: Identity,
    remote_identity: Identity,
    stator: StatorRunner,
    httpx_mock: HTTPXMock,
):
    """
    Validates the "import a CSV of your follows" functionality works
    """
    # Submit the request to the settings view
    csv_file = SimpleUploadedFile(
        "follows.csv",
        b"Account address,Show boosts,Notify on new posts,Languages\ntest@remote.test,true,false,",
    )
    response = client_with_user.post(
        f"/@{identity.handle}/settings/import_export/",
        {
            "csv": csv_file,
            "import_type": "following",
        },
    )
    assert response.status_code == 302

    # It should have made an inbox message to do that follow in the background
    assert InboxMessage.objects.count() == 1

    # Run stator to process it
    stator.run_single_cycle()

    # See if we're now following that identity
    assert identity.outbound_follows.filter(target=remote_identity).count() == 1


@pytest.mark.django_db
def test_export_following(
    client_with_user: Client,
    identity: Identity,
    remote_identity: Identity,
    stator: StatorRunner,
    httpx_mock: HTTPXMock,
):
    """
    Validates the "export a CSV of your follows" functionality works
    """
    # Follow remote_identity
    IdentityService(identity).follow(remote_identity)

    # Download the CSV
    response = client_with_user.get(
        f"/@{identity.handle}/settings/import_export/following.csv"
    )
    assert response.status_code == 200
    assert (
        response.content.strip()
        == b"Account address,Show boosts,Notify on new posts,Languages\r\ntest@remote.test,true,false,"
    )


@pytest.mark.django_db
def test_export_followers(
    client_with_user: Client,
    identity: Identity,
    identity2: Identity,
    stator: StatorRunner,
    httpx_mock: HTTPXMock,
):
    """
    Validates the "export a CSV of your follows" functionality works
    """
    # Follow remote_identity
    IdentityService(identity2).follow(identity)

    # Download the CSV
    response = client_with_user.get(
        f"/@{identity.handle}/settings/import_export/followers.csv"
    )
    assert response.status_code == 200
    assert response.content.strip() == b"Account address\r\ntest@example2.com"
