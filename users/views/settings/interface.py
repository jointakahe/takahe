from activities.models.post import Post
from users.views.settings.settings_page import SettingsPage


class InterfacePage(SettingsPage):

    section = "interface"

    options = {
        "toot_mode": {
            "title": "I Will Toot As I Please",
            "help_text": "Changes all 'Post' buttons to 'Toot!'",
        },
        "default_post_visibility": {
            "title": "Default Post Visibility",
            "help_text": "Visibility to use as default for new posts.",
            "choices": Post.Visibilities.choices,
        },
    }

    layout = {"Posting": ["toot_mode", "default_post_visibility"]}
