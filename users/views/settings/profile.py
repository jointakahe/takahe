from django import forms
from django.core.files import File
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from core.files import resize_image
from core.models.config import Config
from users.decorators import identity_required


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

    def get_initial(self):
        identity = self.request.identity
        return {
            "name": identity.name,
            "summary": identity.summary,
            "icon": identity.icon and identity.icon.url,
            "image": identity.image and identity.image.url,
            "discoverable": identity.discoverable,
            "visible_follows": identity.config_identity.visible_follows,
        }

    def form_valid(self, form):
        # Update basic info
        identity = self.request.identity
        identity.name = form.cleaned_data["name"]
        identity.summary = form.cleaned_data["summary"]
        identity.discoverable = form.cleaned_data["discoverable"]
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if isinstance(icon, File):
            identity.icon.save(
                icon.name,
                resize_image(icon, size=(400, 400)),
            )
        if isinstance(image, File):
            identity.image.save(
                image.name,
                resize_image(image, size=(1500, 500)),
            )
        identity.save()
        # Save profile-specific identity Config
        Config.set_identity(
            identity, "visible_follows", form.cleaned_data["visible_follows"]
        )
        return redirect(".")
