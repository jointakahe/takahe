import io

from django import forms
from django.core.files import File
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView
from PIL import Image, ImageOps

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

    def get_initial(self):
        identity = self.request.identity
        return {
            "name": identity.name,
            "summary": identity.summary,
            "icon": identity.icon and identity.icon.url,
            "image": identity.image and identity.image.url,
            "discoverable": identity.discoverable,
        }

    def resize_image(self, image: File, *, size: tuple[int, int]) -> File:
        with Image.open(image) as img:
            resized_image = ImageOps.fit(img, size)
            new_image_bytes = io.BytesIO()
            resized_image.save(new_image_bytes, format=img.format)
            return File(new_image_bytes)

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
                self.resize_image(icon, size=(400, 400)),
            )
        if isinstance(image, File):
            identity.image.save(
                image.name,
                self.resize_image(image, size=(1500, 500)),
            )
        identity.save()
        return redirect(".")
