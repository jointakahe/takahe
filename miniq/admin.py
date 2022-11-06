from django.contrib import admin

from miniq.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):

    list_display = ["id", "created", "type", "subject", "completed", "failed"]
    ordering = ["-created"]
    actions = ["reset"]

    @admin.action(description="Reset Task")
    def reset(self, request, queryset):
        queryset.update(
            failed=None,
            completed=None,
            locked=None,
            locked_by=None,
            error=None,
        )
