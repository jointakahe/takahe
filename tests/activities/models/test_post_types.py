import pytest

from activities.models import Post
from activities.models.post_types import QuestionData
from core.ld import canonicalise


@pytest.mark.django_db
def test_question_post(config_system, identity, remote_identity, httpx_mock):
    data = {
        "cc": [],
        "id": "https://remote.test/test-actor/statuses/109519951621804608/activity",
        "to": identity.absolute_profile_uri(),
        "type": "Create",
        "actor": "https://remote.test/test-actor/",
        "object": {
            "cc": [],
            "id": "https://remote.test/test-actor/statuses/109519951621804608",
            "to": identity.absolute_profile_uri(),
            "tag": [],
            "url": "https://remote.test/test-actor/109519951621804608",
            "type": "Question",
            "oneOf": [
                {
                    "name": "Option 1",
                    "type": "Note",
                    "replies": {"type": "Collection", "totalItems": 2},
                },
                {
                    "name": "Option 2",
                    "type": "Note",
                    "replies": {"type": "Collection", "totalItems": 1},
                },
            ],
            "content": '<p>This is a poll :python: </p><p><span class="h-card"><a href="https://ehakat.manfre.net/@mike/" class="u-url mention">@<span>mike</span></a></span></p>',
            "endTime": "2022-12-18T22:03:59Z",
            "replies": {
                "id": "https://remote.test/test-actor/statuses/109519951621804608/replies",
                "type": "Collection",
                "first": {
                    "next": "https://remote.test/test-actor/109519951621804608/replies?only_other_accounts=true&page=true",
                    "type": "CollectionPage",
                    "items": [],
                    "partOf": "https://remote.test/test-actor/109519951621804608/replies",
                },
            },
            "published": "2022-12-15T22:03:59Z",
            "attachment": [],
            "contentMap": {
                "en": '<p>This is a poll :python: </p><p><span class="h-card"><a href="https://ehakat.manfre.net/@mike/" class="u-url mention">@<span>mike</span></a></span></p>'
            },
            "as:sensitive": False,
            "attributedTo": "https://remote.test/test-actor/",
            "toot:votersCount": 3,
        },
        "published": "2022-12-15T22:03:59Z",
    }

    post = Post.by_ap(
        data=canonicalise(data["object"], include_security=True), create=True
    )
    assert post.type == Post.Types.question

    question_data = QuestionData.parse_obj(post.type_data)
    assert question_data.voter_count == 3
    assert isinstance(question_data.options, list)
    assert len(question_data.options) == 2
    assert question_data.options[0].votes == 2
    assert question_data.options[1].votes == 1
