from django.contrib import admin

from stator.models import StatorError


@admin.register(StatorError)
class DomainAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "date",
        "model_label",
        "instance_pk",
        "state",
        "error",
    ]
    ordering = ["-date"]
