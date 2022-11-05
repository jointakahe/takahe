from django.contrib import admin

from statuses.models import Status


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    pass
