from django.utils.decorators import method_decorator
from django.views.generic import RedirectView

from users.decorators import identity_required
from users.views.settings.interface import InterfacePage  # noqa
from users.views.settings.profile import ProfilePage  # noqa
from users.views.settings.security import SecurityPage  # noqa
from users.views.settings.settings_page import SettingsPage  # noqa


@method_decorator(identity_required, name="dispatch")
class SettingsRoot(RedirectView):
    pattern_name = "settings_profile"
