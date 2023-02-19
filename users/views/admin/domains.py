from django import forms
from django.core.validators import RegexValidator
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from users.decorators import admin_required
from users.models import Domain, User


class DomainValidator(RegexValidator):
    ul = "\u00a1-\uffff"  # Unicode letters range (must not be a raw string).

    # Host patterns
    hostname_re = (
        r"[a-z" + ul + r"0-9](?:[a-z" + ul + r"0-9-]{0,61}[a-z" + ul + r"0-9])?"
    )
    # Max length for domain name labels is 63 characters per RFC 1034 sec. 3.1
    domain_re = r"(?:\.(?!-)[a-z" + ul + r"0-9-]{1,63}(?<!-))*"
    tld_re = (
        r"\."  # dot
        r"(?!-)"  # can't start with a dash
        r"(?:[a-z" + ul + "-]{2,63}"  # domain label
        r"|xn--[a-z0-9]{1,59})"  # or punycode label
        r"(?<!-)"  # can't end with a dash
        r"\.?"  # may have a trailing dot
    )
    regex = "^" + hostname_re + domain_re + tld_re + "$"
    message = "This does not look like a domain name"


@method_decorator(admin_required, name="dispatch")
class Domains(TemplateView):

    template_name = "admin/domains.html"

    def get_context_data(self):
        return {
            "domains": Domain.objects.filter(local=True).order_by("domain"),
            "section": "domains",
        }


@method_decorator(admin_required, name="dispatch")
class DomainCreate(FormView):

    template_name = "admin/domain_create.html"
    extra_context = {"section": "domains"}

    class form_class(forms.Form):
        domain = forms.CharField(
            help_text="The domain displayed as part of a user's identity.\nCannot be changed after the domain has been created.",
            validators=[DomainValidator()],
        )
        service_domain = forms.CharField(
            help_text="Optional - a domain that serves Takahē if it is not running on the main domain.\nCannot be changed after the domain has been created.\nMust be unique for each display domain!",
            required=False,
            validators=[DomainValidator()],
        )
        public = forms.BooleanField(
            help_text="If any user on this server can create identities under this domain",
            widget=forms.Select(choices=[(True, "Public"), (False, "Private")]),
            required=False,
        )
        default = forms.BooleanField(
            help_text="If this domain is the default option for new identities",
            widget=forms.Select(choices=[(False, "No"), (True, "Yes")]),
            required=False,
        )
        users = forms.CharField(
            label="Permitted Users",
            help_text="If this domain is not public, the email addresses of the users allowed to use it.\nOne email address per line.",
            widget=forms.Textarea,
            required=False,
        )

        def clean_domain(self):
            if Domain.objects.filter(
                models.Q(domain=self.cleaned_data["domain"])
                | models.Q(service_domain=self.cleaned_data["domain"])
            ):
                raise forms.ValidationError("This domain name is already in use")
            return self.cleaned_data["domain"]

        def clean_service_domain(self):
            if not self.cleaned_data["service_domain"]:
                return None
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

        def clean_default(self):
            value = self.cleaned_data["default"]
            if value and not self.cleaned_data.get("public"):
                raise forms.ValidationError("A non-public domain cannot be the default")
            return value

        def clean_users(self):
            if not self.cleaned_data["users"].strip():
                return []
            if self.cleaned_data.get("public"):
                raise forms.ValidationError(
                    "You cannot limit by user when the domain is public"
                )
            # Turn contents into an email set
            user_emails = set()
            for line in self.cleaned_data["users"].splitlines():
                line = line.strip()
                if line:
                    user_emails.add(line)
            # Fetch those users
            users = list(User.objects.filter(email__in=user_emails))
            # See if there's a set difference
            missing_emails = user_emails.difference({user.email for user in users})
            if missing_emails:
                raise forms.ValidationError(
                    "These emails do not have user accounts: "
                    + (", ".join(missing_emails))
                )
            return users

    def form_valid(self, form):
        domain = Domain.objects.create(
            domain=form.cleaned_data["domain"],
            service_domain=form.cleaned_data["service_domain"] or None,
            public=form.cleaned_data["public"],
            default=form.cleaned_data["default"],
            local=True,
        )
        domain.users.set(form.cleaned_data["users"])
        if domain.default:
            Domain.objects.exclude(pk=domain.pk).update(default=False)
        return redirect(Domain.urls.root)


@method_decorator(admin_required, name="dispatch")
class DomainEdit(FormView):

    template_name = "admin/domain_edit.html"
    extra_context = {"section": "domains"}

    class form_class(DomainCreate.form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["domain"].disabled = True
            self.fields["service_domain"].disabled = True

        def clean_domain(self):
            return self.cleaned_data["domain"]

        def clean_service_domain(self):
            return self.cleaned_data["service_domain"]

    def dispatch(self, request, domain):
        self.domain = get_object_or_404(
            Domain.objects.filter(local=True), domain=domain
        )
        return super().dispatch(request)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["domain"] = self.domain
        return context

    def form_valid(self, form):
        self.domain.public = form.cleaned_data["public"]
        self.domain.default = form.cleaned_data["default"]
        self.domain.save()
        self.domain.users.set(form.cleaned_data["users"])
        if self.domain.default:
            Domain.objects.exclude(pk=self.domain.pk).update(default=False)
        return redirect(Domain.urls.root)

    def get_initial(self):
        return {
            "domain": self.domain.domain,
            "service_domain": self.domain.service_domain,
            "public": self.domain.public,
            "default": self.domain.default,
            "users": "\n".join(sorted(user.email for user in self.domain.users.all())),
        }


@method_decorator(admin_required, name="dispatch")
class DomainDelete(TemplateView):

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
        return redirect("admin_domains")
