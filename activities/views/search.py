from django import forms
from django.views.generic import FormView

from users.models import Domain, Identity


class Search(FormView):

    template_name = "activities/search.html"

    class form_class(forms.Form):
        query = forms.CharField(help_text="Search for a user by @username@domain")

    def form_valid(self, form):
        query = form.cleaned_data["query"].lstrip("@").lower()
        results = {"identities": set()}
        # Search identities

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
                results["identities"].add(identity)

        else:
            for identity in Identity.objects.filter(username=query)[:20]:
                results["identities"].add(identity)
            for identity in Identity.objects.filter(username__startswith=query)[:20]:
                results["identities"].add(identity)
        # Render results
        context = self.get_context_data(form=form)
        context["results"] = results
        return self.render_to_response(context)
