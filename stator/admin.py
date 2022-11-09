from django.contrib import admin

from stator.models import StatorTask


@admin.register(StatorTask)
class DomainAdmin(admin.ModelAdmin):
    list_display = ["id", "model_label", "instance_pk", "locked_until"]
