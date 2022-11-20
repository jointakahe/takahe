from django.utils.decorators import method_decorator

from core.models import Config
from users.decorators import admin_required
from users.views.settings import SettingsPage


@method_decorator(admin_required, name="dispatch")
class AdminSettingsPage(SettingsPage):
    """
    Shows a settings page dynamically created from our settings layout
    at the bottom of the page. Don't add this to a URL directly - subclass!
    """

    options_class = Config.SystemOptions

    def load_config(self):
        return Config.load_system()

    def save_config(self, key, value):
        Config.set_system(key, value)


class BasicSettings(AdminSettingsPage):

    section = "basic"

    options = {
        "site_name": {
            "title": "Site Name",
        },
        "highlight_color": {
            "title": "Highlight Color",
            "help_text": "Used for logo background and other highlights",
        },
        "post_length": {
            "title": "Maximum Post Length",
            "help_text": "The maximum number of characters allowed per post",
        },
        "site_about": {
            "title": "About This Site",
            "help_text": "Displayed on the homepage and the about page.\nNewlines are preserved; HTML also allowed.",
            "display": "textarea",
        },
        "site_icon": {
            "title": "Site Icon",
            "help_text": "Minimum size 64x64px. Should be square.",
        },
        "site_banner": {
            "title": "Site Banner",
            "help_text": "Must be at least 650px wide. 3:1 ratio of width:height recommended.",
        },
        "identity_max_per_user": {
            "title": "Maximum Identities Per User",
            "help_text": "Non-admins will be blocked from creating more than this",
        },
        "identity_min_length": {
            "title": "Minimum Length For User Identities",
            "help_text": "Non-admins will be blocked from creating identities shorter than this",
        },
        "signup_allowed": {
            "title": "Signups Allowed",
            "help_text": "If signups are allowed at all",
        },
        "signup_invite_only": {
            "title": "Invite-Only",
            "help_text": "If signups require an invite code",
        },
        "signup_text": {
            "title": "Signup Page Text",
            "help_text": "Shown above the signup form",
            "display": "textarea",
        },
        "restricted_usernames": {
            "title": "Restricted Usernames",
            "help_text": "Usernames that only admins can register for identities. One per line.",
            "display": "textarea",
        },
    }

    layout = {
        "Branding": [
            "site_name",
            "site_about",
            "site_icon",
            "site_banner",
            "highlight_color",
        ],
        "Signups": ["signup_allowed", "signup_invite_only", "signup_text"],
        "Posts": ["post_length"],
        "Identities": [
            "identity_max_per_user",
            "identity_min_length",
            "restricted_usernames",
        ],
    }
