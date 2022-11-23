from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def data_init(self, **kwargs):
        """
        Runs after migrations or flushes to insert anything we need for first
        boot (or post upgrade).
        """
        # Generate the server actor keypair if needed
        from users.models import SystemActor

        SystemActor.generate_keys_if_needed()

    def ready(self) -> None:
        post_migrate.connect(self.data_init, sender=self)
