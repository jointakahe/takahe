from activities.models.post import Post
from users.views.settings.settings_page import SettingsPage


class InterfacePage(SettingsPage):
    section = "interface"

    options = {
        "default_post_visibility": {
            "title": "Default Post Visibility",
            "help_text": "Visibility to use as default for new posts.",
            "choices": Post.Visibilities.choices,
        },
        "default_reply_visibility": {
            "title": "Default Reply Visibility",
            "help_text": "Visibility to use as default for replies.",
            "choices": Post.Visibilities.choices,
        },
        "custom_css": {
            "title": "Custom CSS",
            "help_text": "Theme the website however you'd like, just for you. You should probably not use this unless you know what you're doing.",
            "display": "textarea",
        },
        "light_theme": {
            "title": "Light Mode",
            "help_text": "Use a light theme rather than the default dark theme.",
        },
    }

    layout = {
        "Posting": ["default_post_visibility", "default_reply_visibility"],
        "Appearance": ["light_theme", "custom_css"],
    }
