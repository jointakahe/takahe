from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe

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
    template_name = "admin/settings.html"

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
        "post_minimum_interval": {
            "title": "Minimum Posting Interval",
            "help_text": "The minimum number of seconds a user must wait between posts",
        },
        "content_warning_text": {
            "title": "Content Warning Feature Name",
            "help_text": "What the feature that lets users provide post summaries is called",
        },
        "site_about": {
            "title": "About This Site",
            "help_text": "Displayed on the homepage and the about page.\nUse Markdown for formatting.",
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
            "help_text": "If uninvited signups are allowed.\nInvite codes will always work.",
        },
        "signup_text": {
            "title": "Signup Page Text",
            "help_text": "Shown above the signup form.\nUse Markdown for formatting.",
            "display": "textarea",
        },
        "signup_max_users": {
            "title": "Maximum User Limit",
            "help_text": "Signups will be auto-disabled if your server grows to this many users.\nUse 0 for unlimited.",
        },
        "signup_email_admins": {
            "title": "Email admins on signup",
            "help_text": "Send an email to all admins whenever a new user signs up",
        },
        "restricted_usernames": {
            "title": "Restricted Usernames",
            "help_text": "Usernames that only admins can register for identities. One per line.",
            "display": "textarea",
        },
        "hashtag_unreviewed_are_public": {
            "title": "Unreviewed Hashtags Are Public",
            "help_text": "Public Hashtags may appear in Trending and have a Tags timeline",
        },
        "emoji_unreviewed_are_public": {
            "title": "Unreviewed Emoji Are Public",
            "help_text": "Public Emoji may appear as images, instead of shortcodes",
        },
        "public_timeline": {
            "title": "Public Timeline",
            "help_text": "If enabled, allows anonymous access to the public timeline",
        },
        "site_frontpage_posts": {
            "title": "Show Public Timeline On Front Page",
            "help_text": "Whether to show some recent posts on the logged-out homepage",
        },
        "custom_head": {
            "title": "HTML <head> Extra",
            "help_text": "Add custom HTML to the &lt;head&gt; of all pages (except /djadmin/).\nNote: This can break page rendering/layout.",
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
            "custom_head",
        ],
        "Signups": [
            "signup_allowed",
            "signup_max_users",
            # "signup_email_admins",
            "signup_text",
        ],
        "Posts": [
            "post_length",
            "post_minimum_interval",
            "content_warning_text",
            "hashtag_unreviewed_are_public",
            "emoji_unreviewed_are_public",
        ],
        "Timelines": [
            "public_timeline",
            "site_frontpage_posts",
        ],
        "Identities": [
            "identity_max_per_user",
            "identity_min_length",
            "restricted_usernames",
        ],
    }


cache_field_defaults = {
    "min_value": 0,
    "max_value": 900,
    "step_size": 15,
}


class TuningSettings(AdminSettingsPage):

    section = "tuning"

    options = {
        "cache_timeout_page_default": {
            **cache_field_defaults,
            "title": "Default Timeout",
            "help_text": "The number of seconds to cache a rendered page",
        },
        "cache_timeout_page_timeline": {
            **cache_field_defaults,
            "title": "Timeline Timeout",
            "help_text": "The number of seconds to cache a rendered timeline page",
        },
        "cache_timeout_page_post": {
            **cache_field_defaults,
            "title": "Individual Post Timeout",
            "help_text": mark_safe(
                "The number of seconds to cache a rendered individual Post page<br>Note: This includes the JSON responses to other servers"
            ),
        },
        "cache_timeout_identity_feed": {
            **cache_field_defaults,
            "title": "Identity Feed Timeout",
            "help_text": "The number of seconds to cache a rendered Identity RSS feed",
        },
    }

    layout = {
        "Rendered Page Cache": [
            "cache_timeout_page_default",
            "cache_timeout_page_timeline",
            "cache_timeout_page_post",
        ],
        "RSS Feeds": [
            "cache_timeout_identity_feed",
        ],
    }


class PoliciesSettings(AdminSettingsPage):

    section = "policies"

    options = {
        "policy_terms": {
            "title": "Terms of Service Page",
            "help_text": "Will only be shown if it has content. Use Markdown for formatting.\nIf you would like to redirect elsewhere, enter just a URL.",
            "display": "textarea",
        },
        "policy_privacy": {
            "title": "Privacy Policy Page",
            "help_text": "Will only be shown if it has content. Use Markdown for formatting.\nIf you would like to redirect elsewhere, enter just a URL.",
            "display": "textarea",
        },
        "policy_rules": {
            "title": "Server Rules Page",
            "help_text": "Will only be shown if it has content. Use Markdown for formatting.\nIf you would like to redirect elsewhere, enter just a URL.",
            "display": "textarea",
        },
        "policy_issues": {
            "title": "Report a Problem Page",
            "help_text": "Will only be shown if it has content. Use Markdown for formatting.\nIf you would like to redirect elsewhere, enter just a URL.",
            "display": "textarea",
        },
    }

    layout = {
        "Policies": [
            "policy_rules",
            "policy_terms",
            "policy_privacy",
            "policy_issues",
        ],
    }
