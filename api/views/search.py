from typing import Literal

from ninja import Field

from activities.models import PostInteraction
from activities.services.search import SearchService
from api import schemas
from api.decorators import identity_required
from api.views.base import api_router


@api_router.get("/v2/search", response=schemas.Search)
@identity_required
def search(
    request,
    q: str,
    type: Literal["accounts", "hashtags", "statuses"] | None = None,
    fetch_identities: bool = Field(False, alias="resolve"),
    following: bool = False,
    exclude_unreviewed: bool = False,
    account_id: str | None = None,
    max_id: str | None = None,
    since_id: str | None = None,
    min_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    if limit > 40:
        limit = 40
    result: dict[str, list] = {"accounts": [], "statuses": [], "hashtags": []}
    # We don't support pagination for searches yet
    if max_id or since_id or min_id or offset:
        return result
    # Run search
    searcher = SearchService(q, request.identity)
    search_result = searcher.search_all()
    if type is None or type == "accounts":
        result["accounts"] = [i.to_mastodon_json() for i in search_result["identities"]]
    if type is None or type == "hashtag":
        result["hashtag"] = [h.to_mastodon_json() for h in search_result["hashtags"]]
    if type is None or type == "statuses":
        interactions = PostInteraction.get_post_interactions(
            search_result["posts"], request.identity
        )
        result["statuses"] = [
            p.to_mastodon_json(interactions=interactions)
            for p in search_result["posts"]
        ]
    return result
