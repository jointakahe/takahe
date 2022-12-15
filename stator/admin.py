from django.contrib import admin

from stator.models import Stats


@admin.register(Stats)
class DomainAdmin(admin.ModelAdmin):
    list_display = [
        "model_label",
        "updated",
    ]
    ordering = ["model_label"]

    def has_add_permission(self, request, obj=None):
        return False
