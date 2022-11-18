from django.apps import AppConfig
from pyld import jsonld

from core.ld import builtin_document_loader


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        from core.models import Config

        Config.system = Config.load_system()
        jsonld.set_document_loader(builtin_document_loader)
