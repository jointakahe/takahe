from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self) -> None:
        # Generate the server actor keypair if needed
        from users.models import SystemActor

        SystemActor.generate_keys_if_needed()
