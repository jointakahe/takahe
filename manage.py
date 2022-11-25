#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# List of settings files that should guard against running certain commands
GUARDED_ENVIRONMENTS = [
    "prod",
]

GUARDED_COMMANDS = [
    "test",
]


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "takahe.settings")

    # Guard against running tests in arbitrary environments
    env_name = os.environ.get("TAKAHE_ENVIRONMENT", "dev")
    if env_name in GUARDED_ENVIRONMENTS:
        for cmd in sys.argv:
            if cmd in GUARDED_COMMANDS:
                raise Exception(f"Cannot run {cmd} in {env_name}")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
