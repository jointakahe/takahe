from functools import partial
from typing import ClassVar, Dict

from django import forms
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, RedirectView
from PIL import Image, ImageOps

from core.models import Config
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class SettingsRoot(RedirectView):
    url = "/settings/interface/"


@method_decorator(identity_required, name="dispatch")
class SettingsPage(FormView):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    options_class = Config.IdentityOptions
    template_name = "settings/settings.html"
    section: ClassVar[str]
    options: Dict[str, Dict[str, str]]

    def get_form_class(self):
        # Create the fields dict from the config object
        fields = {}
        for key, details in self.options.items():
            config_field = self.options_class.__fields__[key]
            if config_field.type_ is bool:
                form_field = partial(
                    forms.BooleanField,
                    widget=forms.Select(
                        choices=[(True, "Enabled"), (False, "Disabled")]
                    ),
                )
            elif config_field.type_ is str:
                form_field = forms.CharField
            else:
                raise ValueError(f"Cannot render settings type {config_field.type_}")
            fields[key] = form_field(
                label=details["title"],
                help_text=details.get("help_text", ""),
                required=details.get("required", False),
            )
        # Create a form class dynamically (yeah, right?) and return that
        return type("SettingsForm", (forms.Form,), fields)

    def load_config(self):
        return Config.load_identity(self.request.identity)

    def save_config(self, key, value):
        Config.set_identity(self.request.identity, key, value)

    def get_initial(self):
        config = self.load_config()
        initial = {}
        for key in self.options.keys():
            initial[key] = getattr(config, key)
        return initial

    def get_context_data(self):
        context = super().get_context_data()
        context["section"] = self.section
        return context

    def form_valid(self, form):
        # Save each key
        for field in form:
            self.save_config(
                field.name,
                form.cleaned_data[field.name],
            )
        return redirect(".")


class InterfacePage(SettingsPage):

    section = "interface"

    options = {
        "toot_mode": {
            "title": "I Will Toot As I Please",
            "help_text": "If enabled, changes all 'Post' buttons to 'Toot!'",
        }
    }


@method_decorator(identity_required, name="dispatch")
class ProfilePage(FormView):
    """
    Lets the identity's profile be edited
    """

    template_name = "settings/profile.html"

    class form_class(forms.Form):
        name = forms.CharField(max_length=500)
        summary = forms.CharField(widget=forms.Textarea, required=False)
        icon = forms.ImageField(required=False)
        image = forms.ImageField(required=False)

    def get_initial(self):
        return {
            "name": self.request.identity.name,
            "summary": self.request.identity.summary,
        }

    def get_context_data(self):
        context = super().get_context_data()
        context["section"] = "profile"
        return context

    def form_valid(self, form):
        # Update identity name and summary
        self.request.identity.name = form.cleaned_data["name"]
        self.request.identity.summary = form.cleaned_data["summary"]
        # Resize images
        icon = form.cleaned_data.get("icon")
        image = form.cleaned_data.get("image")
        if icon:
            resized_image = ImageOps.fit(Image.open(icon), (400, 400))
            icon.open()
            resized_image.save(icon)
            self.request.identity.icon = icon
        if image:
            resized_image = ImageOps.fit(Image.open(image), (1500, 500))
            image.open()
            resized_image.save(image)
            self.request.identity.image = image
        self.request.identity.save()
        return redirect(".")
