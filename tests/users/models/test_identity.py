import pytest
from pytest_httpx import HTTPXMock

from core.models import Config
from users.models import Domain, Identity, User
from users.views.identity import CreateIdentity


@pytest.mark.django_db
def test_create_identity_form(config_system, client):
    """ """
    # Make a user
    user = User.objects.create(email="test@example.com")
    admin = User.objects.create(email="admin@example.com", admin=True)
    # Make a domain
    domain = Domain.objects.create(domain="example.com", local=True)
    domain.users.add(user)
    domain.users.add(admin)

    # Test identity_min_length
    data = {
        "username": "a",
        "domain": domain.domain,
        "name": "The User",
    }

    form = CreateIdentity.form_class(user=user, data=data)
    assert not form.is_valid()
    assert "username" in form.errors
    assert "value has at least" in form.errors["username"][0]

    form = CreateIdentity.form_class(user=admin, data=data)
    assert form.errors == {}

    # Test restricted_usernames
    data = {
        "username": "@root",
        "domain": domain.domain,
        "name": "The User",
    }

    form = CreateIdentity.form_class(user=user, data=data)
    assert not form.is_valid()
    assert "username" in form.errors
    assert "restricted to administrators" in form.errors["username"][0]

    form = CreateIdentity.form_class(user=admin, data=data)
    assert form.errors == {}

    # Test valid chars
    data = {
        "username": "@someval!!!!",
        "domain": domain.domain,
        "name": "The User",
    }

    for u in (user, admin):
        form = CreateIdentity.form_class(user=u, data=data)
        assert not form.is_valid()
        assert "username" in form.errors
        assert form.errors["username"][0].startswith("Only the letters")


@pytest.mark.django_db
def test_identity_max_per_user(config_system, client):
    """
    Ensures that the identity limit is functioning
    """
    # Make a user
    user = User.objects.create(email="test@example.com")
    # Make a domain
    domain = Domain.objects.create(domain="example.com", local=True)
    domain.users.add(user)
    # Make an identity for them
    for i in range(Config.system.identity_max_per_user):
        identity = Identity.objects.create(
            actor_uri=f"https://example.com/@test{i}@example.com/actor/",
            username=f"test{i}",
            domain=domain,
            name=f"Test User{i}",
            local=True,
        )
        identity.users.add(user)

    data = {
        "username": "toomany",
        "domain": domain.domain,
        "name": "Too Many",
    }
    form = CreateIdentity.form_class(user=user, data=data)
    assert form.errors["__all__"][0].startswith("You are not allowed more than")

    user.admin = True
    form = CreateIdentity.form_class(user=user, data=data)
    assert form.is_valid()


@pytest.mark.django_db
def test_fetch_actor(httpx_mock, config_system):
    """
    Ensures that making identities via actor fetching works
    """
    # Make a shell remote identity
    identity = Identity.objects.create(
        actor_uri="https://example.com/test-actor/",
        local=False,
    )

    # Trigger actor fetch
    httpx_mock.add_response(
        url="https://example.com/.well-known/webfinger?resource=acct:test@example.com",
        json={
            "subject": "acct:test@example.com",
            "aliases": [
                "https://example.com/test-actor/",
            ],
            "links": [
                {
                    "rel": "http://webfinger.net/rel/profile-page",
                    "type": "text/html",
                    "href": "https://example.com/test-actor/",
                },
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": "https://example.com/test-actor/",
                },
            ],
        },
    )
    httpx_mock.add_response(
        url="https://example.com/test-actor/",
        json={
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://w3id.org/security/v1",
                {
                    "toot": "http://joinmastodon.org/ns#",
                    "featured": {"@id": "toot:featured", "@type": "@id"},
                },
            ],
            "id": "https://example.com/test-actor/",
            "type": "Person",
            "inbox": "https://example.com/test-actor/inbox/",
            "publicKey": {
                "id": "https://example.com/test-actor/#main-key",
                "owner": "https://example.com/test-actor/",
                "publicKeyPem": "-----BEGIN PUBLIC KEY-----\nits-a-faaaake\n-----END PUBLIC KEY-----\n",
            },
            "followers": "https://example.com/test-actor/followers/",
            "following": "https://example.com/test-actor/following/",
            "featured": "https://example.com/test-actor/collections/featured/",
            "icon": {
                "type": "Image",
                "mediaType": "image/jpeg",
                "url": "https://example.com/icon.jpg",
            },
            "image": {
                "type": "Image",
                "mediaType": "image/jpeg",
                "url": "https://example.com/image.jpg",
            },
            "manuallyApprovesFollowers": False,
            "name": "Test User",
            "preferredUsername": "test",
            "published": "2022-11-02T00:00:00Z",
            "summary": "<p>A test user</p>",
            "url": "https://example.com/test-actor/view/",
        },
    )
    httpx_mock.add_response(
        url="https://example.com/test-actor/collections/featured/",
        json={
            "type": "Collection",
            "totalItems": 1,
            "orderedItems": [
                {
                    "id": "https://example.com/test-actor/posts/123456789",
                    "type": "Note",
                    "attributedTo": "https://example.com/test-actor/",
                    "content": "<p>Test post</p>",
                    "published": "2022-11-02T00:00:00Z",
                    "to": "as:Public",
                    "url": "https://example.com/test-actor/posts/123456789",
                }
            ],
        },
    )
    identity.fetch_actor()

    # Verify the data arrived
    identity = Identity.objects.get(pk=identity.pk)
    assert identity.name == "Test User"
    assert identity.username == "test"
    assert identity.domain_id == "example.com"
    assert identity.profile_uri == "https://example.com/test-actor/view/"
    assert identity.inbox_uri == "https://example.com/test-actor/inbox/"
    assert (
        identity.featured_collection_uri
        == "https://example.com/test-actor/collections/featured/"
    )
    assert identity.icon_uri == "https://example.com/icon.jpg"
    assert identity.image_uri == "https://example.com/image.jpg"
    assert identity.summary == "<p>A test user</p>"
    assert "ts-a-faaaake" in identity.public_key


@pytest.mark.django_db
def test_fetch_webfinger_url(httpx_mock: HTTPXMock, config_system):
    """
    Ensures that we can deal with various kinds of webfinger URLs
    """

    # With no host-meta, it should be the default
    assert (
        Identity.fetch_webfinger_url("example.com")
        == "https://example.com/.well-known/webfinger?resource={uri}"
    )

    # Inject a host-meta directing it to a subdomain
    httpx_mock.add_response(
        url="https://example.com/.well-known/host-meta",
        text="""<?xml version="1.0" encoding="UTF-8"?>
        <XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
        <Link rel="lrdd" template="https://fedi.example.com/.well-known/webfinger?resource={uri}"/>
        </XRD>""",
    )
    assert (
        Identity.fetch_webfinger_url("example.com")
        == "https://fedi.example.com/.well-known/webfinger?resource={uri}"
    )

    # Inject a host-meta directing it to a different URL format
    httpx_mock.add_response(
        url="https://example.com/.well-known/host-meta",
        text="""<?xml version="1.0" encoding="UTF-8"?>
        <XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
        <Link rel="lrdd" template="https://example.com/amazing-webfinger?query={uri}"/>
        </XRD>""",
    )
    assert (
        Identity.fetch_webfinger_url("example.com")
        == "https://example.com/amazing-webfinger?query={uri}"
    )

    # Inject a host-meta directing it to a different url THAT SUPPORTS XML ONLY
    # (we want to ignore that one)
    httpx_mock.add_response(
        url="https://example.com/.well-known/host-meta",
        text="""<?xml version="1.0" encoding="UTF-8"?>
        <XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
        <Link rel="lrdd" template="https://xmlfedi.example.com/webfinger?q={uri}" type="application/xrd+xml"/>
        </XRD>""",
    )
    assert (
        Identity.fetch_webfinger_url("example.com")
        == "https://example.com/.well-known/webfinger?resource={uri}"
    )


@pytest.mark.django_db
def test_attachment_to_ap(identity: Identity, config_system):
    """
    Tests identity attachment conversion to AP format.
    """
    identity.metadata = [
        {
            "type": "http://schema.org#PropertyValue",
            "name": "Website",
            "value": "http://example.com",
        }
    ]

    response = identity.to_ap()

    assert response["attachment"]
    assert len(response["attachment"]) == 1

    attachment = response["attachment"][0]

    assert attachment["type"] == "PropertyValue"
    assert attachment["name"] == "Website"
    assert attachment["value"] == (
        '<a href="http://example.com" rel="nofollow">'
        '<span class="invisible">http://</span>example.com</a>'
    )
