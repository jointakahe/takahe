from django import forms
from django.utils.decorators import method_decorator
from django.views.generic import FormView, RedirectView, TemplateView

from users.decorators import admin_required
from users.models import Identity, User
from users.views.admin.domains import (  # noqa
    DomainCreate,
    DomainDelete,
    DomainEdit,
    Domains,
)
from users.views.admin.federation import FederationEdit, FederationRoot  # noqa
from users.views.admin.hashtags import (  # noqa
    HashtagCreate,
    HashtagDelete,
    HashtagEdit,
    Hashtags,
)
from users.views.admin.settings import (  # noqa
    BasicSettings,
    PoliciesSettings,
    TuningSettings,
)


@method_decorator(admin_required, name="dispatch")
class AdminRoot(RedirectView):
    pattern_name = "admin_basic"


@method_decorator(admin_required, name="dispatch")
class Users(TemplateView):

    template_name = "admin/users.html"

    def get_context_data(self):
        return {
            "users": User.objects.order_by("email"),
            "section": "users",
        }


@method_decorator(admin_required, name="dispatch")
class Identities(TemplateView):

    template_name = "admin/identities.html"

    def get_context_data(self):
        return {
            "identities": Identity.objects.order_by("username"),
            "section": "identities",
        }


@method_decorator(admin_required, name="dispatch")
class Invites(FormView):

    template_name = "admin/invites.html"
    extra_context = {"section": "invites"}

    class form_class(forms.Form):
        note = forms.CharField()

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        return context
