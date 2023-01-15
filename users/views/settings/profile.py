from django import forms
from django.core.files import File
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from core.html import html_to_plaintext
from core.models.config import Config
from users.decorators import identity_required
from users.models import IdentityStates
from users.services import IdentityService


@method_decorator(identity_required, name="dispatch")
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
            help_text="If this user is visible on the frontpage and in user directories.",
            widget=forms.Select(
                choices=[(True, "Discoverable"), (False, "Not Discoverable")]
            ),
            required=False,
        )
        visible_follows = forms.BooleanField(
            help_text="Whether or not to show your following and follower counts in your profile.",
            widget=forms.Select(choices=[(True, "Visible"), (False, "Hidden")]),
            required=False,
        )
        metadata = forms.JSONField(
            label="Profile Metadata Fields",
            help_text="These values will appear on your profile below your Bio",
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

    def get_initial(self):
        identity = self.request.identity
        return {
            "name": identity.name,
            "summary": html_to_plaintext(identity.summary) if identity.summary else "",
            "icon": identity.icon and identity.icon.url,
            "image": identity.image and identity.image.url,
            "discoverable": identity.discoverable,
            "visible_follows": identity.config_identity.visible_follows,
            "metadata": identity.metadata or [],
        }

    def form_valid(self, form):
        # Update basic info
        identity = self.request.identity
        service = IdentityService(identity)
        identity.name = form.cleaned_data["name"]
        identity.discoverable = form.cleaned_data["discoverable"]
        service.set_summary(form.cleaned_data["summary"])
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if isinstance(icon, File):
            service.set_icon(icon)
        if isinstance(image, File):
            service.set_image(image)
        identity.metadata = form.cleaned_data.get("metadata")

        # Clear images if specified
        if "icon__clear" in self.request.POST:
            identity.icon = None
        if "image__clear" in self.request.POST:
            identity.image = None

        # Save and propagate
        identity.save()
        identity.transition_perform(IdentityStates.edited)

        # Save profile-specific identity Config
        Config.set_identity(
            identity, "visible_follows", form.cleaned_data["visible_follows"]
        )
        return redirect(".")
