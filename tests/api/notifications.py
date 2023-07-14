import pytest

from activities.models import TimelineEvent


@pytest.mark.django_db
def test_notifications(api_client, identity, remote_identity):
    event = TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    data = api_client.get("/api/v1/notifications").json()
    assert len(data) == 1
    assert data[0]["type"] == "follow"
    assert data[0]["account"]["id"] == str(remote_identity.id)

    event.delete()


@pytest.mark.django_db
def test_get_notification(api_client, identity, remote_identity):
    event = TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    data = api_client.get(f"/api/v1/notifications/{event.id}").json()
    assert data["type"] == "follow"
    assert data["account"]["id"] == str(remote_identity.id)

    event.delete()


@pytest.mark.django_db
def test_dismiss_notifications(api_client, identity, identity2, remote_identity):
    TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=identity2,
    )
    TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    data = api_client.get("/api/v1/notifications").json()
    assert len(data) == 2

    response = api_client.post("/api/v1/notifications/clear", {})
    assert response.status_code == 200
    assert response.json() == {}

    data = api_client.get("/api/v1/notifications").json()
    assert len(data) == 0

    TimelineEvent.objects.filter(identity=identity).delete()


@pytest.mark.django_db
def test_dismiss_notification(api_client, identity, remote_identity):
    event = TimelineEvent.objects.create(
        identity=identity,
        type=TimelineEvent.Types.followed,
        subject_identity=remote_identity,
    )

    data = api_client.get("/api/v1/notifications").json()
    assert len(data) == 1

    response = api_client.post(f"/api/v1/notifications/{event.id}/dismiss", {})
    assert response.status_code == 200
    assert response.json() == {}

    data = api_client.get("/api/v1/notifications").json()
    assert len(data) == 0

    TimelineEvent.objects.filter(identity=identity).delete()
