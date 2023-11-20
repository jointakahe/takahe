import pytest
from pytest_httpx import HTTPXMock

test_account_json = r"""
{
   "@context":[
      "https://www.w3.org/ns/activitystreams",
      "https://w3id.org/security/v1",
      {
         "manuallyApprovesFollowers":"as:manuallyApprovesFollowers",
         "toot":"http://joinmastodon.org/ns#",
         "featured":{
            "@id":"toot:featured",
            "@type":"@id"
         },
         "featuredTags":{
            "@id":"toot:featuredTags",
            "@type":"@id"
         },
         "movedTo":{
            "@id":"as:movedTo",
            "@type":"@id"
         },
         "schema":"http://schema.org#",
         "PropertyValue":"schema:PropertyValue",
         "value":"schema:value",
         "discoverable":"toot:discoverable",
         "Device":"toot:Device",
         "deviceId":"toot:deviceId",
         "messageType":"toot:messageType",
         "cipherText":"toot:cipherText",
         "suspended":"toot:suspended",
         "memorial":"toot:memorial",
         "indexable":"toot:indexable"
      }
   ],
   "id":"https://search.example.com/users/searchtest",
   "type":"Person",
   "following":"https://search.example.com/users/searchtest/following",
   "followers":"https://search.example.com/users/searchtest/followers",
   "inbox":"https://search.example.com/users/searchtest/inbox",
   "outbox":"https://search.example.com/users/searchtest/outbox",
   "featured":"https://search.example.com/users/searchtest/collections/featured",
   "featuredTags":"https://search.example.com/users/searchtest/collections/tags",
   "preferredUsername":"searchtest",
   "name":"searchtest",
   "summary":"<p>Just a test (àáâãäåæ)</p>",
   "url":"https://search.example.com/@searchtest",
   "manuallyApprovesFollowers":false,
   "discoverable":true,
   "indexable":false,
   "published":"2018-05-09T00:00:00Z",
   "memorial":false,
   "devices":"https://search.example.com/users/searchtest/collections/devices",
   "endpoints":{
      "sharedInbox":"https://search.example.com/inbox"
   }
}
"""


@pytest.mark.django_db
def test_search_not_found(httpx_mock: HTTPXMock, api_client):
    httpx_mock.add_response(status_code=404)
    response = api_client.get(
        "/api/v2/search",
        content_type="application/json",
        data={
            "q": "https://notfound.example.com",
        },
    ).json()

    assert response["accounts"] == []
    assert response["statuses"] == []
    assert response["hashtags"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "encoding",
    [
        "utf-8",
        "iso-8859-1",
    ],
)
@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/ld+json",
        "application/activity+json",
    ],
)
def test_search(
    content_type: str,
    encoding: str,
    httpx_mock: HTTPXMock,
    api_client,
):
    httpx_mock.add_response(
        headers={"Content-Type": f"{content_type}; charset={encoding}"},
        content=test_account_json.encode(encoding),
    )

    response = api_client.get(
        "/api/v2/search",
        content_type="application/json",
        data={
            "q": "https://search.example.com/users/searchtest",
        },
    ).json()

    assert len(response["accounts"]) == 1
    assert response["accounts"][0]["acct"] == "searchtest@search.example.com"
    assert response["accounts"][0]["username"] == "searchtest"
    assert response["accounts"][0]["note"] == "<p>Just a test (àáâãäåæ)</p>"
