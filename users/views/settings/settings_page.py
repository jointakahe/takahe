from functools import partial
from typing import ClassVar

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from core.models.config import Config, UploadedImage
from users.shortcuts import by_handle_or_404


@method_decorator(login_required, name="dispatch")
class SettingsPage(FormView):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    options_class = Config.IdentityOptions
    template_name = "settings/settings.html"
    section: ClassVar[str]
    options: dict[str, dict[str, str | int]]
    layout: dict[str, list[str]]

    def get_form_class(self):
        # Create the fields dict from the config object
        fields = {}
        for key, details in self.options.items():
            field_kwargs = {}
            config_field = self.options_class.__fields__[key]
            if config_field.type_ is bool:
                form_field = partial(
                    forms.BooleanField,
                    widget=forms.Select(
                        choices=[(True, "Enabled"), (False, "Disabled")]
                    ),
                )
            elif config_field.type_ is UploadedImage:
                form_field = forms.ImageField
            elif config_field.type_ is str:
                if details.get("display") == "textarea":
                    form_field = partial(
                        forms.CharField,
                        widget=forms.Textarea,
                    )
                else:
                    form_field = forms.CharField
            elif config_field.type_ is int:
                choices = details.get("choices")
                if choices:
                    field_kwargs["widget"] = forms.Select(choices=choices)
                for int_kwarg in {"min_value", "max_value", "step_size"}:
                    val = details.get(int_kwarg)
                    if val:
                        field_kwargs[int_kwarg] = val
                form_field = forms.IntegerField
            else:
                raise ValueError(f"Cannot render settings type {config_field.type_}")
            fields[key] = form_field(
                label=details["title"],
                help_text=details.get("help_text", ""),
                required=details.get("required", False),
                **field_kwargs,
            )
        # Create a form class dynamically (yeah, right?) and return that
        return type("SettingsForm", (forms.Form,), fields)

    def dispatch(self, request, *args, **kwargs):
        if "handle" in kwargs:
            self.identity = by_handle_or_404(request, kwargs["handle"])
        return super().dispatch(request, *args, **kwargs)

    def load_config(self):
        return Config.load_identity(self.identity)

    def save_config(self, key, value):
        Config.set_identity(self.identity, key, value)

    def get_initial(self):
        config = self.load_config()
        initial = {}
        for key in self.options.keys():
            initial[key] = getattr(config, key)
        return initial

    def get_context_data(self):
        context = super().get_context_data()
        context["section"] = self.section
        # Gather fields into fieldsets
        context["fieldsets"] = {}
        for title, fields in self.layout.items():
            context["fieldsets"][title] = [context["form"][field] for field in fields]
        if hasattr(self, "identity"):
            context["identity"] = self.identity
        return context

    def form_valid(self, form):
        # Save each key
        for field in form:
            if field.field.__class__.__name__ == "ImageField":
                # These can be cleared with an extra checkbox
                if self.request.POST.get(f"{field.name}__clear"):
                    self.save_config(field.name, None)
                    continue
                # We shove the preview values in initial_data, so only save file
                # fields if they have a File object.
                if not isinstance(form.cleaned_data[field.name], File):
                    continue
            self.save_config(
                field.name,
                form.cleaned_data[field.name],
            )
        messages.success(self.request, "Your settings have been saved.")
        return redirect(".")


class UserSettingsPage(SettingsPage):
    """
    User-option oriented version of the settings page.
    """

    options_class = Config.UserOptions

    def load_config(self):
        return Config.load_user(self.request.user)

    def save_config(self, key, value):
        Config.set_user(self.request.user, key, value)
