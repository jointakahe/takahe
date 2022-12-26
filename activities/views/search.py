from django import forms
from django.views.generic import FormView

from activities.services import SearchService


class Search(FormView):

    template_name = "activities/search.html"

    class form_class(forms.Form):
        query = forms.CharField(
            help_text="Search for:\nA user by @username@domain or their profile URL\nA hashtag by #tagname\nA post by its URL",
            widget=forms.TextInput(attrs={"type": "search", "autofocus": "autofocus"}),
        )

    def form_valid(self, form):
        searcher = SearchService(form.cleaned_data["query"], self.request.identity)
        # Render results
        context = self.get_context_data(form=form)
        context["results"] = searcher.search_all()
        return self.render_to_response(context)
