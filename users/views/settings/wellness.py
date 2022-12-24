from users.views.settings.settings_page import SettingsPage


class WellnessPage(SettingsPage):

    section = "wellness"

    options = {
        "visible_reaction_counts": {
            "title": "Show Boost and Like Counts",
            "help_text": "Disable to hide the number of Likes and Boosts on a 'Post'",
        },
    }

    layout = {"Wellness": ["visible_reaction_counts"]}
