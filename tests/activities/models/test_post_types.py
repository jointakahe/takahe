import pytest

from activities.models import Post
from activities.models.post_types import QuestionData
from core.ld import canonicalise


@pytest.mark.django_db
def test_question_post(config_system, identity, remote_identity):
    data = {
        "cc": [],
        "id": "https://fosstodon.org/users/manfre/statuses/109519951621804608/activity",
        "to": identity.absolute_profile_uri(),
        "type": "Create",
        "actor": "https://fosstodon.org/users/manfre",
        "object": {
            "cc": [],
            "id": "https://fosstodon.org/users/manfre/statuses/109519951621804608",
            "to": identity.absolute_profile_uri(),
            "tag": [],
            "url": "https://fosstodon.org/@manfre/109519951621804608",
            "type": "Question",
            "oneOf": [
                {
                    "name": "Option 1",
                    "type": "Note",
                    "replies": {"type": "Collection", "totalItems": 0},
                },
                {
                    "name": "Option 2",
                    "type": "Note",
                    "replies": {"type": "Collection", "totalItems": 0},
                },
            ],
            "content": '<p>This is a poll :python: </p><p><span class="h-card"><a href="https://ehakat.manfre.net/@mike/" class="u-url mention">@<span>mike</span></a></span></p>',
            "endTime": "2022-12-18T22:03:59Z",
            "replies": {
                "id": "https://fosstodon.org/users/manfre/statuses/109519951621804608/replies",
                "type": "Collection",
                "first": {
                    "next": "https://fosstodon.org/users/manfre/statuses/109519951621804608/replies?only_other_accounts=true&page=true",
                    "type": "CollectionPage",
                    "items": [],
                    "partOf": "https://fosstodon.org/users/manfre/statuses/109519951621804608/replies",
                },
            },
            "published": "2022-12-15T22:03:59Z",
            "attachment": [],
            "contentMap": {
                "en": '<p>This is a poll :python: </p><p><span class="h-card"><a href="https://ehakat.manfre.net/@mike/" class="u-url mention">@<span>mike</span></a></span></p>'
            },
            "as:sensitive": False,
            "attributedTo": "https://fosstodon.org/users/manfre",
            "http://ostatus.org#atomUri": "https://fosstodon.org/users/manfre/statuses/109519951621804608",
            "http://ostatus.org#conversation": "tag:fosstodon.org,2022-12-15:objectId=69494364:objectType=Conversation",
            "http://joinmastodon.org/ns#votersCount": 0,
        },
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1",
        ],
        "published": "2022-12-15T22:03:59Z",
    }

    post = Post.by_ap(
        data=canonicalise(data["object"], include_security=True), create=True
    )
    assert post.type == Post.Types.question
    QuestionData.parse_obj(post.type_data)
