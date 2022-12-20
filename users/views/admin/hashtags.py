from django import forms
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from activities.models import Hashtag, HashtagStates
from users.decorators import moderator_required


@method_decorator(moderator_required, name="dispatch")
class Hashtags(TemplateView):

    template_name = "admin/hashtags.html"

    def get_context_data(self):
        return {
            "hashtags": Hashtag.objects.filter().order_by("hashtag"),
            "section": "hashtag",
        }


@method_decorator(moderator_required, name="dispatch")
class HashtagCreate(FormView):

    template_name = "admin/hashtag_create.html"
    extra_context = {"section": "hashtags"}

    class form_class(forms.Form):
        hashtag = forms.SlugField(
            help_text="The hashtag without the '#'",
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

        def clean_hashtag(self):
            hashtag = self.cleaned_data["hashtag"].lstrip("#").lower()
            if not Hashtag.hashtag_regex.match("#" + hashtag):
                raise forms.ValidationError("This does not look like a hashtag name")
            if Hashtag.objects.filter(hashtag=hashtag):
                raise forms.ValidationError("This hashtag name is already in use")
            return hashtag

        def clean_name_override(self):
            name_override = self.cleaned_data["name_override"]
            if not name_override:
                return None
            if self.cleaned_data["hashtag"] != name_override.lower():
                raise forms.ValidationError(
                    "Name override doesn't match hashtag. Only case changes are allowed."
                )
            return self.cleaned_data["name_override"]

    def form_valid(self, form):
        Hashtag.objects.create(
            hashtag=form.cleaned_data["hashtag"],
            name_override=form.cleaned_data["name_override"] or None,
            public=form.cleaned_data["public"],
        )
        return redirect(Hashtag.urls.root)


@method_decorator(moderator_required, name="dispatch")
class HashtagEdit(FormView):

    template_name = "admin/hashtag_edit.html"
    extra_context = {"section": "hashtags"}

    class form_class(HashtagCreate.form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["hashtag"].disabled = True

        def clean_hashtag(self):
            return self.cleaned_data["hashtag"]

    def dispatch(self, request, hashtag):
        self.hashtag = get_object_or_404(Hashtag.objects, hashtag=hashtag)
        return super().dispatch(request)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["hashtag"] = self.hashtag
        return context

    def form_valid(self, form):
        self.hashtag.public = form.cleaned_data["public"]
        self.hashtag.name_override = form.cleaned_data["name_override"]
        self.hashtag.save()
        Hashtag.transition_perform(self.hashtag, HashtagStates.outdated)
        return redirect(Hashtag.urls.root)

    def get_initial(self):
        return {
            "hashtag": self.hashtag.hashtag,
            "name_override": self.hashtag.name_override,
            "public": self.hashtag.public,
        }


@method_decorator(moderator_required, name="dispatch")
class HashtagDelete(TemplateView):

    template_name = "admin/hashtag_delete.html"

    def dispatch(self, request, hashtag):
        self.hashtag = get_object_or_404(Hashtag.objects, hashtag=hashtag)
        return super().dispatch(request)

    def get_context_data(self):
        return {
            "hashtag": self.hashtag,
            "section": "hashtags",
        }

    def post(self, request):
        self.hashtag.delete()
        return redirect("admin_hashtags")
