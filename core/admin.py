from django.contrib import admin

from core.models import Config


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "key", "user", "identity"]
