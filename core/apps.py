from django.apps import AppConfig
from pyld import jsonld

from core.ld import caching_document_loader


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self) -> None:
        jsonld.set_document_loader(caching_document_loader)
