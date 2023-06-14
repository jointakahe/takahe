from django import forms
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView, View
from django_htmx.http import HttpResponseClientRefresh

from activities.models import Hashtag, HashtagStates
from users.decorators import moderator_required


@method_decorator(moderator_required, name="dispatch")
class Hashtags(ListView):

    template_name = "admin/hashtags.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.extra_context = {
            "section": "hashtags",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Hashtag.objects.filter().order_by("hashtag")


@method_decorator(moderator_required, name="dispatch")
class HashtagEdit(FormView):

    template_name = "admin/hashtag_edit.html"
    extra_context = {"section": "hashtags"}

    class form_class(forms.Form):
        hashtag = forms.SlugField(
            help_text="The hashtag without the '#'",
            disabled=True,
        )
        name_override = forms.CharField(
            help_text="Optional - a more human readable hashtag.",
            required=False,
        )
        public = forms.NullBooleanField(
            help_text="Should this hashtag appear in the UI",
            widget=forms.Select(
                choices=[(None, "Unreviewed"), (True, "Public"), (False, "Private")]
            ),
            required=False,
        )

        def clean_name_override(self):
            name_override = self.cleaned_data["name_override"]
            if not name_override:
                return None
            if self.cleaned_data["hashtag"] != name_override.lower():
                raise forms.ValidationError(
                    "Name override doesn't match hashtag. Only case changes are allowed."
                )
            return self.cleaned_data["name_override"]

    def dispatch(self, request, hashtag):
        self.hashtag = get_object_or_404(Hashtag.objects, hashtag=hashtag)
        return super().dispatch(request)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["hashtag"] = self.hashtag
        context["page"] = self.request.GET.get("page")
        return context

    def form_valid(self, form):
        self.hashtag.public = form.cleaned_data["public"]
        self.hashtag.name_override = form.cleaned_data["name_override"]
        self.hashtag.save()
        Hashtag.transition_perform(self.hashtag, HashtagStates.outdated)
        return redirect(Hashtag.urls.admin)

    def get_initial(self):
        return {
            "hashtag": self.hashtag.hashtag,
            "name_override": self.hashtag.name_override,
            "public": self.hashtag.public,
        }


@method_decorator(moderator_required, name="dispatch")
class HashtagEnable(View):
    """
    Sets a hashtag to be enabled (or not!)
    """

    enable = True

    def post(self, request, hashtag):
        self.hashtag = get_object_or_404(Hashtag, hashtag=hashtag)
        self.hashtag.public = self.enable
        self.hashtag.save()
        return HttpResponseClientRefresh()
