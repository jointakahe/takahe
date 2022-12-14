from django.contrib import admin

from api.models import Application, Token


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "website", "created"]


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "application", "created"]
