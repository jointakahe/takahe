from django import forms
from django.utils.decorators import method_decorator
from django.views.generic import FormView, RedirectView

from users.decorators import admin_required
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
from users.views.admin.identities import IdentitiesRoot, IdentityEdit  # noqa
from users.views.admin.settings import (  # noqa
    BasicSettings,
    PoliciesSettings,
    TuningSettings,
)
from users.views.admin.stator import Stator  # noqa
from users.views.admin.users import UserEdit, UsersRoot  # noqa


@method_decorator(admin_required, name="dispatch")
class AdminRoot(RedirectView):
    pattern_name = "admin_basic"


@method_decorator(admin_required, name="dispatch")
class Invites(FormView):

    template_name = "admin/invites.html"
    extra_context = {"section": "invites"}

    class form_class(forms.Form):
        note = forms.CharField()

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        return context
