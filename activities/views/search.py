from django import forms
from django.views.generic import FormView

from users.models import Identity


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
            for identity in Identity.objects.filter(
                domain_id=domain, username=username
            )[:20]:
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
