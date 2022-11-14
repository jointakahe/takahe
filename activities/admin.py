from django.contrib import admin

from activities.models import FanOut, Post, PostInteraction, TimelineEvent


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "author", "created"]
    raw_id_fields = ["to", "mentions"]
    actions = ["force_fetch"]

    @admin.action(description="Force Fetch")
    def force_fetch(self, request, queryset):
        for instance in queryset:
            instance.debug_fetch()


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ["id", "identity", "created", "type"]
    raw_id_fields = ["identity", "subject_post", "subject_identity"]


@admin.register(FanOut)
class FanOutAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "type", "identity"]
    raw_id_fields = ["identity", "subject_post"]


@admin.register(PostInteraction)
class PostInteractionAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "type", "identity", "post"]
    raw_id_fields = ["identity", "post"]
