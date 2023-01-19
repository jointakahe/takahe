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
        "visible_reaction_counts": {
            "title": "Show Boost and Like Counts",
            "help_text": "Disable to hide the number of Likes and Boosts on a 'Post'",
        },
        "custom_css": {
            "title": "Custom CSS",
            "help_text": "Theme the website however you'd like, just for you. You should probably not use this unless you know what you're doing.",
            "display": "textarea",
        },
        "expand_linked_cws": {
            "title": "Expand linked Content Warnings",
            "help_text": "Expands all CWs of the same type at once, rather than one at a time.",
        },
        "infinite_scroll": {
            "title": "Infinite Scroll",
            "help_text": "Automatically loads more posts when you get to the bottom of a timeline.",
        },
        "light_theme": {
            "title": "Light Mode",
            "help_text": "Use a light theme rather than the default dark theme.",
        },
    }

    layout = {
        "Posting": ["toot_mode", "default_post_visibility"],
        "Wellness": ["infinite_scroll", "visible_reaction_counts", "expand_linked_cws"],
        "Appearance": ["light_theme", "custom_css"],
    }
