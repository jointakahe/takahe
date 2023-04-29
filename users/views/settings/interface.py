from users.views.settings.settings_page import UserSettingsPage


class InterfacePage(UserSettingsPage):
    section = "interface"

    options = {
        "light_theme": {
            "title": "Light Theme",
            "help_text": "Use a light theme when you are logged in to the web interface",
        },
    }

    layout = {
        "Appearance": ["light_theme"],
    }
