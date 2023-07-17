import httpx

from activities.models import Hashtag, Post
from core.ld import canonicalise
from users.models import Domain, Identity, IdentityStates
from users.models.system_actor import SystemActor


class SearchService:
    """
    Captures the logic needed to search - reused in the UI and API
    """

    def __init__(self, query: str, identity: Identity | None):
        self.query = query.strip()
        self.identity = identity

    def search_identities_handle(self) -> set[Identity]:
        """
        Searches for identities by their handles
        """

        # Short circuit if it's obviously not for us
        if "://" in self.query:
            return set()

        # Try to fetch the user by handle
        handle = self.query.lstrip("@")
        results: set[Identity] = set()
        if "@" in handle:
            username, domain = handle.split("@", 1)

            # Resolve the domain to the display domain
            domain_instance = Domain.get_domain(domain)
            try:
                if domain_instance is None:
                    raise Identity.DoesNotExist()
                identity = Identity.objects.get(
                    domain=domain_instance,
                    username__iexact=username,
                )
            except Identity.DoesNotExist:
                identity = None
                if self.identity is not None:
                    try:
                        # Allow authenticated users to fetch remote
                        identity = Identity.by_username_and_domain(
                            username, domain_instance or domain, fetch=True
                        )
                        if identity and identity.state == IdentityStates.outdated:
                            identity.fetch_actor()
                    except ValueError:
                        pass

            if identity:
                results.add(identity)

        else:
            for identity in Identity.objects.filter(username=handle)[:20]:
                results.add(identity)
            for identity in Identity.objects.filter(username__istartswith=handle)[:20]:
                results.add(identity)
        return results

    def search_url(self) -> Post | Identity | None:
        """
        Searches for an identity or post by URL.
        """

        # Short circuit if it's obviously not for us
        if "://" not in self.query:
            return None

        # Fetch the provided URL as the system actor to retrieve the AP JSON
        try:
            response = SystemActor().signed_request(
                method="get",
                uri=self.query,
            )
        except httpx.RequestError:
            return None
        if response.status_code >= 400:
            return None
        document = canonicalise(response.json(), include_security=True)
        type = document.get("type", "unknown").lower()

        # Is it an identity?
        if type in Identity.ACTOR_TYPES:
            # Try and retrieve the profile by actor URI
            identity = Identity.by_actor_uri(document["id"], create=True)
            if identity and identity.state == IdentityStates.outdated:
                identity.fetch_actor()
            return identity

        # Is it a post?
        elif type in [value.lower() for value in Post.Types.values]:
            # Try and retrieve the post by URI
            # (we do not trust the JSON we just got - fetch from source!)
            try:
                return Post.by_object_uri(document["id"], fetch=True)
            except Post.DoesNotExist:
                return None

        # Dunno what it is
        else:
            return None

    def search_hashtags(self) -> set[Hashtag]:
        """
        Searches for hashtags by their name
        """

        # Short circuit out if it's obviously not a hashtag
        if "@" in self.query or "://" in self.query:
            return set()

        results: set[Hashtag] = set()
        name = self.query.lstrip("#").lower()
        for hashtag in Hashtag.objects.public().hashtag_or_alias(name)[:10]:
            results.add(hashtag)
        for hashtag in Hashtag.objects.public().filter(hashtag__startswith=name)[:10]:
            results.add(hashtag)
        return results

    def search_post_content(self):
        """
        Searches for posts on an identity via full text search
        """
        return self.identity.posts.unlisted(include_replies=True).filter(
            content__search=self.query
        )[:50]

    def search_all(self):
        """
        Returns all possible results for a search
        """
        results = {
            "identities": self.search_identities_handle(),
            "hashtags": self.search_hashtags(),
            "posts": set(),
        }
        url_result = self.search_url()
        if isinstance(url_result, Identity):
            results["identities"].add(url_result)
        if isinstance(url_result, Post):
            results["posts"].add(url_result)
        return results
