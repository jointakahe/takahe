from typing import Set

from django import forms
from django.views.generic import FormView

from activities.models import Hashtag
from users.models import Domain, Identity


class Search(FormView):

    template_name = "activities/search.html"

    class form_class(forms.Form):
        query = forms.CharField(
            help_text="Search for a user by @username@domain or hashtag by #tagname"
        )

    def search_identities(self, query: str):
        query = query.lstrip("@")
        results: Set[Identity] = set()
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
                identity = None
            if identity:
                results.add(identity)

        else:
            for identity in Identity.objects.filter(username=query)[:20]:
                results.add(identity)
            for identity in Identity.objects.filter(username__startswith=query)[:20]:
                results.add(identity)
        return results

    def search_hashtags(self, query: str):
        results: Set[Hashtag] = set()

        if "@" in query:
            return results

        query = query.lstrip("#")
        for hashtag in Hashtag.objects.public().hashtag_or_alias(query)[:10]:
            results.add(hashtag)
        for hashtag in Hashtag.objects.public().filter(hashtag__startswith=query)[:10]:
            results.add(hashtag)
        return results

    def form_valid(self, form):
        query = form.cleaned_data["query"].lower()
        results = {
            "identities": self.search_identities(query),
            "hashtags": self.search_hashtags(query),
        }

        # Render results
        context = self.get_context_data(form=form)
        context["results"] = results
        return self.render_to_response(context)
