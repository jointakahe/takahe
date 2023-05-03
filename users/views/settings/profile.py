from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from core.html import FediverseHtmlParser
from core.models.config import Config
from users.models import IdentityStates
from users.services import IdentityService
from users.shortcuts import by_handle_or_404


@method_decorator(login_required, name="dispatch")
class ProfilePage(FormView):
    """
    Lets the identity's profile be edited
    """

    template_name = "settings/profile.html"
    extra_context = {"section": "profile"}

    class form_class(forms.Form):
        name = forms.CharField(max_length=500)
        summary = forms.CharField(
            widget=forms.Textarea,
            required=False,
            help_text="Describe you and your interests",
            label="Bio",
        )
        icon = forms.ImageField(
            required=False, help_text="Shown next to all your posts and activities"
        )
        image = forms.ImageField(
            required=False, help_text="Shown at the top of your profile"
        )
        discoverable = forms.BooleanField(
            help_text="If this user is visible on the frontpage and in user directories",
            widget=forms.Select(
                choices=[(True, "Discoverable"), (False, "Not Discoverable")]
            ),
            required=False,
        )
        visible_follows = forms.BooleanField(
            help_text="Whether or not to show your following and follower counts in your profile",
            widget=forms.Select(choices=[(True, "Visible"), (False, "Hidden")]),
            required=False,
        )
        search_enabled = forms.BooleanField(
            help_text="If a search feature is provided for your posts on the profile page\n(Disabling this will not prevent third-party search crawlers from indexing your posts)",
            widget=forms.Select(choices=[(True, "Enabled"), (False, "Disabled")]),
            required=False,
        )
        metadata = forms.JSONField(
            label="Profile Metadata Fields",
            help_text="These values will appear on your profile below your bio",
            widget=forms.HiddenInput(attrs={"data-min-empty": 2}),
            required=False,
        )

        def clean_metadata(self):
            metadata = self.cleaned_data["metadata"]
            if metadata:
                metadata = [x for x in metadata if x["name"] and x["value"]]
            if not metadata:
                return None
            return metadata

    def dispatch(self, request, handle: str, *args, **kwargs):
        self.identity = by_handle_or_404(self.request, handle, local=True, fetch=False)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["identity"] = self.identity
        return context

    def get_initial(self):
        return {
            "name": self.identity.name,
            "summary": (
                FediverseHtmlParser(self.identity.summary).plain_text
                if self.identity.summary
                else ""
            ),
            "icon": self.identity.icon and self.identity.icon.url,
            "image": self.identity.image and self.identity.image.url,
            "discoverable": self.identity.discoverable,
            "visible_follows": self.identity.config_identity.visible_follows,
            "metadata": self.identity.metadata or [],
            "search_enabled": self.identity.config_identity.search_enabled,
        }

    def form_valid(self, form):
        # Update basic info
        service = IdentityService(self.identity)
        self.identity.name = form.cleaned_data["name"]
        self.identity.discoverable = form.cleaned_data["discoverable"]
        service.set_summary(form.cleaned_data["summary"])
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if isinstance(icon, File):
            service.set_icon(icon)
        if isinstance(image, File):
            service.set_image(image)
        self.identity.metadata = form.cleaned_data.get("metadata")

        # Clear images if specified
        if "icon__clear" in self.request.POST:
            self.identity.icon = None
        if "image__clear" in self.request.POST:
            self.identity.image = None

        # Save and propagate
        self.identity.save()
        self.identity.transition_perform(IdentityStates.edited)

        # Save profile-specific identity Config
        Config.set_identity(
            self.identity, "visible_follows", form.cleaned_data["visible_follows"]
        )
        Config.set_identity(
            self.identity, "search_enabled", form.cleaned_data["search_enabled"]
        )

        messages.success(self.request, "Your profile has been updated.")
        return redirect(".")
