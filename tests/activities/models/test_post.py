import pytest
from pytest_httpx import HTTPXMock

from activities.models import Post, PostStates
from activities.models.post_types import QuestionData
from users.models import Identity, InboxMessage


@pytest.mark.django_db
def test_fetch_post(httpx_mock: HTTPXMock, config_system):
    """
    Tests that a post we don't have locally can be fetched by by_object_uri
    """
    httpx_mock.add_response(
        url="https://example.com/test-actor",
        json={
            "@context": [
                "https://www.w3.org/ns/activitystreams",
            ],
            "id": "https://example.com/test-actor",
            "type": "Person",
        },
    )
    httpx_mock.add_response(
        url="https://example.com/test-post",
        json={
            "@context": [
                "https://www.w3.org/ns/activitystreams",
            ],
            "id": "https://example.com/test-post",
            "type": "Note",
            "published": "2022-11-13T23:20:16Z",
            "url": "https://example.com/test-post",
            "attributedTo": "https://example.com/test-actor",
            "content": "BEEEEEES",
        },
    )
    # Fetch with a HTTP access
    post = Post.by_object_uri("https://example.com/test-post", fetch=True)
    assert post.content == "BEEEEEES"
    assert post.author.actor_uri == "https://example.com/test-actor"
    # Fetch again with a DB hit
    assert Post.by_object_uri("https://example.com/test-post").id == post.id


@pytest.mark.django_db
def test_post_create_edit(identity: Identity, config_system):
    """
    Tests that creating/editing a post works, and extracts mentions and hashtags.
    """
    post = Post.create_local(author=identity, content="Hello #world I am @test")
    assert post.hashtags == ["world"]
    assert list(post.mentions.all()) == [identity]

    post.edit_local(content="Now I like #hashtags")
    assert post.hashtags == ["hashtags"]
    assert list(post.mentions.all()) == []


@pytest.mark.django_db
def test_linkify_mentions_remote(
    identity, identity2, remote_identity, remote_identity2
):
    """
    Tests that we can linkify post mentions properly for remote use
    """
    # Test a short username (remote)
    post = Post.objects.create(
        content="<p>Hello @test</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_remote()
        == '<p>Hello <a href="https://remote.test/@test/">@test</a></p>'
    )
    # Test a full username (local)
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(identity)
    assert (
        post.safe_content_remote()
        == '<p><a href="https://example.com/@test/">@test</a>, welcome!</p>'
    )
    # Test that they don't get touched without a mention
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    assert post.safe_content_remote() == "<p>@test@example.com, welcome!</p>"

    # Test case insensitivity (remote)
    post = Post.objects.create(
        content="<p>Hey @TeSt</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_remote()
        == '<p>Hey <a href="https://remote.test/@test/">@TeSt</a></p>'
    )

    # Test trailing dot (remote)
    post = Post.objects.create(
        content="<p>Hey @test@remote.test.</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_remote()
        == '<p>Hey <a href="https://remote.test/@test/">@test</a>.</p>'
    )

    # Test that collapsing only applies to the first unique, short username
    post = Post.objects.create(
        content="<p>Hey @TeSt@remote.test and @test@remote2.test</p>",
        author=identity,
        local=True,
    )
    post.mentions.set([remote_identity, remote_identity2])
    assert post.safe_content_remote() == (
        '<p>Hey <a href="https://remote.test/@test/">@TeSt</a> '
        'and <a href="https://remote2.test/@test/">@test@remote2.test</a></p>'
    )

    post.content = "<p>Hey @TeSt, @Test@remote.test and @test</p>"
    assert post.safe_content_remote() == (
        '<p>Hey <a href="https://remote2.test/@test/">@TeSt</a>, '
        '<a href="https://remote.test/@test/">@Test@remote.test</a> '
        'and <a href="https://remote2.test/@test/">@test</a></p>'
    )


@pytest.mark.django_db
def test_linkify_mentions_local(config_system, identity, identity2, remote_identity):
    """
    Tests that we can linkify post mentions properly for local use
    """
    # Test a short username (remote)
    post = Post.objects.create(
        content="<p>Hello @test</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert (
        post.safe_content_local()
        == '<p>Hello <a href="/@test@remote.test/">@test</a></p>'
    )
    # Test a full username (local)
    post = Post.objects.create(
        content="<p>@test@example.com, welcome! @test@example2.com @test@example.com</p>",
        author=identity,
        local=True,
    )
    post.mentions.add(identity)
    post.mentions.add(identity2)
    assert post.safe_content_local() == (
        '<p><a href="/@test@example.com/">@test</a>, welcome!'
        ' <a href="/@test@example2.com/">@test@example2.com</a>'
        ' <a href="/@test@example.com/">@test</a></p>'
    )
    # Test a full username (remote) with no <p>
    post = Post.objects.create(
        content="@test@remote.test hello!",
        author=identity,
        local=True,
    )
    post.mentions.add(remote_identity)
    assert post.safe_content_local() == '<a href="/@test@remote.test/">@test</a> hello!'
    # Test that they don't get touched without a mention
    post = Post.objects.create(
        content="<p>@test@example.com, welcome!</p>",
        author=identity,
        local=True,
    )
    assert post.safe_content_local() == "<p>@test@example.com, welcome!</p>"


@pytest.mark.django_db
def test_post_transitions(identity, stator):

    # Create post
    post = Post.objects.create(
        content="<p>Hello!</p>",
        author=identity,
        local=False,
        visibility=Post.Visibilities.mentioned,
    )
    # Test: | --> new --> fanned_out
    assert post.state == str(PostStates.new)
    stator.run_single_cycle_sync()
    post = Post.objects.get(id=post.id)
    assert post.state == str(PostStates.fanned_out)

    # Test: fanned_out --> (forced) edited --> edited_fanned_out
    Post.transition_perform(post, PostStates.edited)
    stator.run_single_cycle_sync()
    post = Post.objects.get(id=post.id)
    assert post.state == str(PostStates.edited_fanned_out)

    # Test: edited_fanned_out --> (forced) deleted --> deleted_fanned_out
    Post.transition_perform(post, PostStates.deleted)
    stator.run_single_cycle_sync()
    post = Post.objects.get(id=post.id)
    assert post.state == str(PostStates.deleted_fanned_out)


@pytest.mark.django_db
def test_content_map(remote_identity):
    """
    Tests that post contentmap content also works
    """
    post = Post.by_ap(
        data={
            "id": "https://remote.test/posts/1/",
            "type": "Note",
            "content": "Hi World",
            "attributedTo": "https://remote.test/test-actor/",
            "published": "2022-12-23T10:50:54Z",
        },
        create=True,
    )
    assert post.content == "Hi World"

    post2 = Post.by_ap(
        data={
            "id": "https://remote.test/posts/2/",
            "type": "Note",
            "contentMap": {"und": "Hey World"},
            "attributedTo": "https://remote.test/test-actor/",
            "published": "2022-12-23T10:50:54Z",
        },
        create=True,
    )
    assert post2.content == "Hey World"

    post3 = Post.by_ap(
        data={
            "id": "https://remote.test/posts/3/",
            "type": "Note",
            "contentMap": {"en-gb": "Hello World"},
            "attributedTo": "https://remote.test/test-actor/",
            "published": "2022-12-23T10:50:54Z",
        },
        create=True,
    )
    assert post3.content == "Hello World"


@pytest.mark.django_db
def test_content_map_question(remote_identity: Identity):
    """
    Tests post contentmap for questions
    """
    post = Post.by_ap(
        data={
            "id": "https://remote.test/posts/1/",
            "type": "Question",
            "votersCount": 10,
            "closed": "2023-01-01T26:04:45Z",
            "content": "Test Question",
            "attributedTo": "https://remote.test/test-actor/",
            "published": "2022-12-23T10:50:54Z",
            "endTime": "2023-01-01T20:04:45Z",
            "oneOf": [
                {
                    "type": "Note",
                    "name": "Option 1",
                    "replies": {
                        "type": "Collection",
                        "totalItems": 6,
                    },
                },
                {
                    "type": "Note",
                    "name": "Option 2",
                    "replies": {
                        "type": "Collection",
                        "totalItems": 4,
                    },
                },
            ],
        },
        create=True,
    )
    assert post.content == "Test Question"
    assert isinstance(post.type_data, QuestionData)
    assert post.type_data.voter_count == 10

    # test the update case
    question_id = post.id

    post = Post.by_ap(
        data={
            "id": "https://remote.test/posts/1/",
            "type": "Question",
            "votersCount": 100,
            "closed": "2023-01-01T26:04:45Z",
            "content": "Test Question",
            "attributedTo": "https://remote.test/test-actor/",
            "published": "2022-12-23T10:50:54Z",
            "endTime": "2023-01-01T20:04:45Z",
            "oneOf": [
                {
                    "type": "Note",
                    "name": "Option 1",
                    "replies": {
                        "type": "Collection",
                        "totalItems": 60,
                    },
                },
                {
                    "type": "Note",
                    "name": "Option 2",
                    "replies": {
                        "type": "Collection",
                        "totalItems": 40,
                    },
                },
            ],
        },
        create=False,
        update=True,
    )
    assert isinstance(post.type_data, QuestionData)
    assert post.type_data.voter_count == 100
    assert post.id == question_id


@pytest.mark.django_db
@pytest.mark.parametrize("delete_type", ["note", "tombstone", "ref"])
def test_inbound_posts(
    remote_identity: Identity,
    stator,
    delete_type: bool,
):
    """
    Ensures that a remote post can arrive via inbox message, be edited, and be
    deleted.
    """
    # Create an inbound new post message
    message = {
        "id": "test",
        "type": "Create",
        "actor": remote_identity.actor_uri,
        "object": {
            "id": "https://remote.test/test-post",
            "type": "Note",
            "published": "2022-11-13T23:20:16Z",
            "attributedTo": remote_identity.actor_uri,
            "content": "post version one",
        },
    }
    InboxMessage.objects.create(message=message)

    # Run stator and ensure that made the post
    print("prestat")
    stator.run_single_cycle_sync()
    print("poststat")
    post = Post.objects.get(object_uri="https://remote.test/test-post")
    assert post.content == "post version one"
    assert post.published.day == 13
    assert post.url == "https://remote.test/test-post"

    # Create an inbound post edited message
    message = {
        "id": "test",
        "type": "Update",
        "actor": remote_identity.actor_uri,
        "object": {
            "id": "https://remote.test/test-post",
            "type": "Note",
            "published": "2022-11-13T23:20:16Z",
            "updated": "2022-11-14T23:20:16Z",
            "url": "https://remote.test/test-post/display",
            "attributedTo": remote_identity.actor_uri,
            "content": "post version two",
        },
    }
    InboxMessage.objects.create(message=message)

    # Run stator and ensure that edited the post
    stator.run_single_cycle_sync()
    post = Post.objects.get(object_uri="https://remote.test/test-post")
    assert post.content == "post version two"
    assert post.edited.day == 14
    assert post.url == "https://remote.test/test-post/display"

    # Create an inbound post deleted message
    if delete_type == "ref":
        message = {
            "id": "test",
            "type": "Delete",
            "actor": remote_identity.actor_uri,
            "object": "https://remote.test/test-post",
        }
    elif delete_type == "tombstone":
        message = {
            "id": "test",
            "type": "Delete",
            "actor": remote_identity.actor_uri,
            "object": {
                "id": "https://remote.test/test-post",
                "type": "Tombstone",
            },
        }
    else:
        message = {
            "id": "test",
            "type": "Delete",
            "actor": remote_identity.actor_uri,
            "object": {
                "id": "https://remote.test/test-post",
                "type": "Note",
                "published": "2022-11-13T23:20:16Z",
                "attributedTo": remote_identity.actor_uri,
            },
        }
    InboxMessage.objects.create(message=message)

    # Run stator and ensure that deleted the post
    stator.run_single_cycle_sync()
    assert not Post.objects.filter(object_uri="https://remote.test/test-post").exists()
