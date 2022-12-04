import httpx
from asgiref.sync import async_to_sync
from django import forms
from django.views.generic import FormView

from activities.models import Hashtag, Post
from core.ld import canonicalise
from users.models import Domain, Identity, IdentityStates
from users.models.system_actor import SystemActor


class Search(FormView):

    template_name = "activities/search.html"

    class form_class(forms.Form):
        query = forms.CharField(
            help_text="Search for:\nA user by @username@domain or their profile URL\nA hashtag by #tagname\nA post by its URL",
            widget=forms.TextInput(attrs={"type": "search", "autofocus": "autofocus"}),
        )

    def search_identities_handle(self, query: str):
        """
        Searches for identities by their handles
        """

        # Short circuit if it's obviously not for us
        if "://" in query:
            return set()

        # Try to fetch the user by handle
        query = query.lstrip("@")
        results: set[Identity] = set()
        if "@" in query:
            username, domain = query.split("@", 1)

            # Resolve the domain to the display domain
            domain_instance = Domain.get_domain(domain)
            try:
                if domain_instance is None:
                    raise Identity.DoesNotExist()
                identity = Identity.objects.get(
                    domain=domain_instance, username=username
                )
            except Identity.DoesNotExist:
                if self.request.identity is not None:
                    # Allow authenticated users to fetch remote
                    identity = Identity.by_username_and_domain(
                        username, domain, fetch=True
                    )
                    if identity and identity.state == IdentityStates.outdated:
                        async_to_sync(identity.fetch_actor)()
                else:
                    identity = None
            if identity:
                results.add(identity)

        else:
            for identity in Identity.objects.filter(username=query)[:20]:
                results.add(identity)
            for identity in Identity.objects.filter(username__startswith=query)[:20]:
                results.add(identity)
        return results

    def search_url(self, query: str) -> Post | Identity | None:
        """
        Searches for an identity or post by URL.
        """

        # Short circuit if it's obviously not for us
        if "://" not in query:
            return None

        # Clean up query
        query = query.strip()

        # Fetch the provided URL as the system actor to retrieve the AP JSON
        try:
            response = async_to_sync(SystemActor().signed_request)(
                method="get", uri=query
            )
        except (httpx.RequestError, httpx.ConnectError):
            return None
        if response.status_code >= 400:
            return None
        document = canonicalise(response.json(), include_security=True)
        type = document.get("type", "unknown").lower()

        # Is it an identity?
        if type == "person":
            # Try and retrieve the profile by actor URI
            identity = Identity.by_actor_uri(document["id"], create=True)
            if identity and identity.state == IdentityStates.outdated:
                async_to_sync(identity.fetch_actor)()
            return identity

        # Is it a post?
        elif type == "note":
            # Try and retrieve the post by URI
            # (we do not trust the JSON we just got - fetch from source!)
            try:
                return Post.by_object_uri(document["id"], fetch=True)
            except Post.DoesNotExist:
                return None

        # Dunno what it is
        else:
            return None

    def search_hashtags(self, query: str):
        """
        Searches for hashtags by their name
        """

        # Short circuit out if it's obviously not a hashtag
        if "@" in query or "://" in query:
            return set()

        results: set[Hashtag] = set()
        query = query.lstrip("#")
        for hashtag in Hashtag.objects.public().hashtag_or_alias(query)[:10]:
            results.add(hashtag)
        for hashtag in Hashtag.objects.public().filter(hashtag__startswith=query)[:10]:
            results.add(hashtag)
        return results

    def form_valid(self, form):
        query = form.cleaned_data["query"].lower()
        results = {
            "identities": self.search_identities_handle(query),
            "hashtags": self.search_hashtags(query),
            "posts": set(),
        }

        url_result = self.search_url(query)
        if isinstance(url_result, Identity):
            results["identities"].add(url_result)
        if isinstance(url_result, Post):
            results["posts"].add(url_result)

        # Render results
        context = self.get_context_data(form=form)
        context["results"] = results
        return self.render_to_response(context)
