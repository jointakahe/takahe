import pytest

from activities.models import TimelineEvent


@pytest.mark.django_db
def test_notifications(api_client, identity, remote_identity):
    event = TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    response = api_client.get("/api/v1/notifications").json()

    assert len(response) == 1
    assert response[0]["type"] == "follow"
    assert response[0]["account"]["id"] == str(remote_identity.id)

    event.delete()


@pytest.mark.django_db
def test_get_notification(api_client, identity, remote_identity):
    event = TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    response = api_client.get(f"/api/v1/notifications/{event.id}").json()
    assert response["type"] == "follow"
    assert response["account"]["id"] == str(remote_identity.id)

    event.delete()
