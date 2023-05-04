from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import View

from users.views.settings.delete import DeleteIdentity  # noqa
from users.views.settings.follows import FollowsPage  # noqa
from users.views.settings.import_export import (  # noqa
    CsvFollowers,
    CsvFollowing,
    ImportExportPage,
)
from users.views.settings.interface import InterfacePage  # noqa
from users.views.settings.posting import PostingPage  # noqa
from users.views.settings.profile import ProfilePage  # noqa
from users.views.settings.security import SecurityPage  # noqa
from users.views.settings.settings_page import SettingsPage  # noqa
from users.views.settings.tokens import TokenCreate, TokenEdit, TokensRoot  # noqa


@method_decorator(login_required, name="dispatch")
class SettingsRoot(View):
    """
    Redirects to a root settings page (varying on if there is an identity
    in the URL or not)
    """

    def get(self, request, handle: str | None = None):
        if handle:
            return redirect("settings_profile", handle=handle)
        return redirect("settings_security")
