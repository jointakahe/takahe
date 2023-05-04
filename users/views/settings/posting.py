from activities.models.post import Post
from users.views.settings.settings_page import SettingsPage


class PostingPage(SettingsPage):
    section = "posting"

    options = {
        "default_post_visibility": {
            "title": "Default Post Visibility",
            "help_text": "Visibility to use as default for new posts.",
            "choices": Post.Visibilities.choices,
        },
    }

    layout = {
        "Posting": ["default_post_visibility"],
    }
