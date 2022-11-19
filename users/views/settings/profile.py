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

    def form_valid(self, form):
        # Update identity name and summary
        self.request.identity.name = form.cleaned_data["name"]
        self.request.identity.summary = form.cleaned_data["summary"]
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if isinstance(icon, File):
            resized_image = ImageOps.fit(Image.open(icon), (400, 400))
            new_icon_bytes = io.BytesIO()
            resized_image.save(new_icon_bytes, format=icon.format)
            self.request.identity.icon.save(icon.name, File(new_icon_bytes))
        if isinstance(image, File):
            resized_image = ImageOps.fit(Image.open(image), (400, 400))
            new_image_bytes = io.BytesIO()
            resized_image.save(new_image_bytes, format=image.format)
            self.request.identity.image.save(image.name, File(new_image_bytes))
        self.request.identity.save()
        return redirect(".")
