from functools import partial
from typing import ClassVar, Dict

from django import forms
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, RedirectView

from core.models import Config
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class SystemSettingsRoot(RedirectView):
    url = "/settings/system/basic/"


@method_decorator(identity_required, name="dispatch")
class SystemSettingsPage(FormView):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    template_name = "settings/settings_system.html"
    options_class = Config.SystemOptions
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
        return Config.load_system()

    def save_config(self, key, value):
        Config.set_system(key, value)

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


class BasicPage(SystemSettingsPage):

    section = "basic"

    options = {
        "site_name": {
            "title": "Site Name",
            "help_text": "Shown in the top-left of the page, and titles",
        },
        "highlight_color": {
            "title": "Highlight Color",
            "help_text": "Used for logo background and other highlights",
        },
    }
