from django.utils.decorators import method_decorator
from django.views.generic import RedirectView

from core.models import Config
from users.decorators import identity_required
from users.views.admin import AdminSettingsPage


@method_decorator(identity_required, name="dispatch")
class SettingsRoot(RedirectView):
    url = "/settings/interface/"


class SettingsPage(AdminSettingsPage):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    options_class = Config.IdentityOptions
    template_name = "settings/settings.html"

    def load_config(self):
        return Config.load_identity(self.request.identity)

    def save_config(self, key, value):
        Config.set_identity(self.request.identity, key, value)


class InterfacePage(SettingsPage):

    section = "interface"

    options = {
        "toot_mode": {
            "title": "I Will Toot As I Please",
            "help_text": "If enabled, changes all 'Post' buttons to 'Toot!'",
        }
    }
