from asgiref.sync import async_to_sync
from django.contrib import admin

from activities.models import (
    FanOut,
    Hashtag,
    Post,
    PostAttachment,
    PostInteraction,
    TimelineEvent,
)


@admin.register(Hashtag)
class HashtagAdmin(admin.ModelAdmin):
    list_display = ["hashtag", "name_override", "state", "stats_updated", "created"]

    readonly_fields = ["created", "updated", "stats_updated"]

    actions = ["force_execution"]

    @admin.action(description="Force Execution")
    def force_execution(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")


@admin.register(PostAttachment)
class PostAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "created"]


class PostAttachmentInline(admin.StackedInline):
    model = PostAttachment
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "author", "created"]
    raw_id_fields = ["to", "mentions", "author"]
    actions = ["force_fetch", "reparse_hashtags"]
    search_fields = ["content"]
    inlines = [PostAttachmentInline]
    readonly_fields = ["created", "updated", "object_json"]

    @admin.action(description="Force Fetch")
    def force_fetch(self, request, queryset):
        for instance in queryset:
            instance.debug_fetch()

    @admin.action(description="Reprocess content for hashtags")
    def reparse_hashtags(self, request, queryset):
        for instance in queryset:
            instance.hashtags = Hashtag.hashtags_from_content(instance.content) or None
            instance.save()
            async_to_sync(instance.ensure_hashtags)()

    @admin.display(description="ActivityPub JSON")
    def object_json(self, instance):
        return instance.to_ap()

    def has_add_permission(self, request, obj=None):
        """
        Disables admin creation of posts as it will skip steps
        """
        return False


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ["id", "identity", "created", "type"]
    readonly_fields = ["created"]
    raw_id_fields = [
        "identity",
        "subject_post",
        "subject_identity",
        "subject_post_interaction",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FanOut)
class FanOutAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "type", "identity"]
    raw_id_fields = ["identity", "subject_post", "subject_post_interaction"]
    readonly_fields = ["created", "updated"]
    actions = ["force_execution"]

    @admin.action(description="Force Execution")
    def force_execution(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("new")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PostInteraction)
class PostInteractionAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "type", "identity", "post"]
    raw_id_fields = ["identity", "post"]

    def has_add_permission(self, request, obj=None):
        return False
