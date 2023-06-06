import pycountry

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
        "expand_content_warnings": {
            "title": "Expand content warnings",
            "help_text": "If content warnings should be expanded by default (not honoured by all clients)",
        },
        "preferred_posting_language": {
            "title": "Default posting language",
            "help_text": "",
            "choices": sorted(
                (
                    [
                        ("", ""),
                    ]
                    + [
                        (lang.alpha_2, lang.name)
                        for lang in pycountry.languages
                        if hasattr(lang, "alpha_2")
                    ]
                ),
                key=lambda lang: lang[1],
            ),
        },
    }

    layout = {
        "Posting": [
            "default_post_visibility",
            "expand_content_warnings",
            "preferred_posting_language",
        ],
    }
