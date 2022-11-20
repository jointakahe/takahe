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

    def get_initial(self):
        return {
            "name": self.request.identity.name,
            "summary": self.request.identity.summary,
            "icon": self.request.identity.icon and self.request.identity.icon.url,
            "image": self.request.identity.image and self.request.identity.image.url,
        }

    def resize_image(self, image: File, *, size: tuple[int, int]) -> File:
        with Image.open(image) as img:
            resized_image = ImageOps.fit(img, size)
            new_image_bytes = io.BytesIO()
            resized_image.save(new_image_bytes, format=img.format)
            return File(new_image_bytes)

    def form_valid(self, form):
        # Update identity name and summary
        self.request.identity.name = form.cleaned_data["name"]
        self.request.identity.summary = form.cleaned_data["summary"]
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if isinstance(icon, File):
            self.request.identity.icon.save(
                icon.name,
                self.resize_image(icon, size=(400, 400)),
            )
        if isinstance(image, File):
            self.request.identity.image.save(
                image.name,
                self.resize_image(image, size=(400, 400)),
            )
        self.request.identity.save()
        return redirect(".")
