from users.views.settings.settings_page import SettingsPage


class PrivacyPage(SettingsPage):

    section = "privacy"

    options = {
        "visible_follows": {
            "title": "Visible Follows",
            "help_text": "Whether or not to show your following and follower counts in your profile.",
        },
    }

    layout = {
        "Profile": ["visible_follows"],
    }
