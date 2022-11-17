import re
from functools import partial
from typing import ClassVar, Dict

from django import forms
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, RedirectView, TemplateView

from core.models import Config
from users.decorators import admin_required
from users.models import Domain, Identity, User


@method_decorator(admin_required, name="dispatch")
class AdminRoot(RedirectView):
    pattern_name = "admin_basic"


@method_decorator(admin_required, name="dispatch")
class AdminSettingsPage(FormView):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    template_name = "admin/settings.html"
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


class BasicPage(AdminSettingsPage):

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


@method_decorator(admin_required, name="dispatch")
class DomainsPage(TemplateView):

    template_name = "admin/domains.html"

    def get_context_data(self):
        return {
            "domains": Domain.objects.filter(local=True).order_by("domain"),
            "section": "domains",
        }


@method_decorator(admin_required, name="dispatch")
class DomainCreatePage(FormView):

    template_name = "admin/domain_create.html"
    extra_context = {"section": "domains"}

    class form_class(forms.Form):
        domain = forms.CharField(
            help_text="The domain displayed as part of a user's identity.\nCannot be changed after the domain has been created.",
        )
        service_domain = forms.CharField(
            help_text="Optional - a domain that serves Takahē if it is not running on the main domain.\nCannot be changed after the domain has been created.",
            required=False,
        )
        public = forms.BooleanField(
            help_text="If any user on this server can create identities here",
            widget=forms.Select(choices=[(True, "Public"), (False, "Private")]),
            required=False,
        )

        domain_regex = re.compile(
            r"^((?!-))(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]{0,1}\.(xn--)?([a-z0-9\-]{1,61}|[a-z0-9-]{1,30}\.[a-z]{2,})$"
        )

        def clean_domain(self):
            if not self.domain_regex.match(self.cleaned_data["domain"]):
                raise forms.ValidationError("This does not look like a domain name")
            if Domain.objects.filter(
                models.Q(domain=self.cleaned_data["domain"])
                | models.Q(service_domain=self.cleaned_data["domain"])
            ):
                raise forms.ValidationError("This domain name is already in use")
            return self.cleaned_data["domain"]

        def clean_service_domain(self):
            if not self.cleaned_data["service_domain"]:
                return None
            if not self.domain_regex.match(self.cleaned_data["service_domain"]):
                raise forms.ValidationError("This does not look like a domain name")
            if Domain.objects.filter(
                models.Q(domain=self.cleaned_data["service_domain"])
                | models.Q(service_domain=self.cleaned_data["service_domain"])
            ):
                raise forms.ValidationError("This domain name is already in use")
            if self.cleaned_data.get("domain") == self.cleaned_data["service_domain"]:
                raise forms.ValidationError(
                    "You cannot have the domain and service domain be the same (did you mean to leave service domain blank?)"
                )
            return self.cleaned_data["service_domain"]

    def form_valid(self, form):
        Domain.objects.create(
            domain=form.cleaned_data["domain"],
            service_domain=form.cleaned_data["service_domain"] or None,
            public=form.cleaned_data["public"],
            local=True,
        )
        return redirect(Domain.urls.root)


@method_decorator(admin_required, name="dispatch")
class DomainEditPage(FormView):

    template_name = "admin/domain_edit.html"
    extra_context = {"section": "domains"}

    class form_class(forms.Form):
        domain = forms.CharField(
            help_text="The domain displayed as part of a user's identity.\nCannot be changed after the domain has been created.",
            disabled=True,
        )
        service_domain = forms.CharField(
            help_text="Optional - a domain that serves Takahē if it is not running on the main domain.\nCannot be changed after the domain has been created.",
            disabled=True,
            required=False,
        )
        public = forms.BooleanField(
            help_text="If any user on this server can create identities here",
            widget=forms.Select(choices=[(True, "Public"), (False, "Private")]),
            required=False,
        )

    def dispatch(self, request, domain):
        self.domain = get_object_or_404(
            Domain.objects.filter(local=True), domain=domain
        )
        return super().dispatch(request)

    def get_context_data(self):
        context = super().get_context_data()
        context["domain"] = self.domain
        return context

    def form_valid(self, form):
        self.domain.public = form.cleaned_data["public"]
        self.domain.save()
        return redirect(Domain.urls.root)

    def get_initial(self):
        return {
            "domain": self.domain.domain,
            "service_domain": self.domain.service_domain,
            "public": self.domain.public,
        }


@method_decorator(admin_required, name="dispatch")
class DomainDeletePage(TemplateView):

    template_name = "admin/domain_delete.html"

    def dispatch(self, request, domain):
        self.domain = get_object_or_404(
            Domain.objects.filter(public=True), domain=domain
        )
        return super().dispatch(request)

    def get_context_data(self):
        return {
            "domain": self.domain,
            "num_identities": self.domain.identities.count(),
            "section": "domains",
        }

    def post(self, request):
        if self.domain.identities.exists():
            raise ValueError("Tried to delete domain with identities!")
        self.domain.delete()
        return redirect("/settings/system/domains/")


@method_decorator(admin_required, name="dispatch")
class UsersPage(TemplateView):

    template_name = "admin/users.html"

    def get_context_data(self):
        return {
            "users": User.objects.order_by("email"),
            "section": "users",
        }


@method_decorator(admin_required, name="dispatch")
class IdentitiesPage(TemplateView):

    template_name = "admin/identities.html"

    def get_context_data(self):
        return {
            "identities": Identity.objects.order_by("username"),
            "section": "identities",
        }
