from asgiref.sync import async_to_sync
from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from activities.models import (
    Emoji,
    FanOut,
    Hashtag,
    Post,
    PostAttachment,
    PostInteraction,
    TimelineEvent,
)


class IdentityLocalFilter(admin.SimpleListFilter):
    title = _("Local Identity")
    parameter_name = "islocal"

    identity_field_name = "identity"

    def lookups(self, request, model_admin):
        return (
            ("1", _("Yes")),
            ("0", _("No")),
        )

    def queryset(self, request, queryset):
        match self.value():
            case "1":
                return queryset.filter(**{f"{self.identity_field_name}__local": True})
            case "0":
                return queryset.filter(**{f"{self.identity_field_name}__local": False})
            case _:
                return queryset


@admin.register(Hashtag)
class HashtagAdmin(admin.ModelAdmin):
    list_display = ["hashtag", "name_override", "state", "stats_updated", "created"]
    list_filter = ("public", "state", "stats_updated")
    search_fields = ["hashtag", "aliases"]

    readonly_fields = ["created", "updated", "stats_updated"]

    actions = ["force_state_outdated", "force_state_updated"]

    @admin.action(description="Force State: outdated")
    def force_state_outdated(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

    @admin.action(description="Force State: updated")
    def force_state_updated(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("updated")


@admin.register(Emoji)
class EmojiAdmin(admin.ModelAdmin):
    list_display = (
        "shortcode",
        "preview",
        "local",
        "domain",
        "public",
        "state",
        "created",
    )
    list_filter = ("local", "public", "state")
    search_fields = ("shortcode",)

    readonly_fields = ["preview", "created", "updated", "to_ap_tag"]

    actions = ["force_execution", "approve_emoji", "reject_emoji"]

    @admin.action(description="Force Execution")
    def force_execution(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

    @admin.action(description="Approve Emoji")
    def approve_emoji(self, request, queryset):
        queryset.update(public=True)

    @admin.action(description="Reject Emoji")
    def reject_emoji(self, request, queryset):
        queryset.update(public=False)

    @admin.display(description="Emoji Preview")
    def preview(self, instance):
        if instance.public is False:
            return mark_safe(f'<a href="{instance.full_url().relative}">Preview</a>')
        return mark_safe(
            f'<img src="{instance.full_url().relative}" style="height: 22px">'
        )


@admin.register(PostAttachment)
class PostAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "created"]


class PostAttachmentInline(admin.StackedInline):
    model = PostAttachment
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "type", "author", "state", "created"]
    list_filter = ("type", "local", "visibility", "state", "created")
    raw_id_fields = ["to", "mentions", "author", "emojis"]
    actions = ["reparse_hashtags"]
    search_fields = ["content"]
    inlines = [PostAttachmentInline]
    readonly_fields = ["created", "updated", "state_changed", "object_json"]

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
    list_display = ["id", "identity", "published", "type"]
    list_filter = (IdentityLocalFilter, "type")
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
    list_display = ["id", "state", "created", "state_attempted", "type", "identity"]
    list_filter = (IdentityLocalFilter, "type", "state", "state_attempted")
    raw_id_fields = ["identity", "subject_post", "subject_post_interaction"]
    readonly_fields = ["created", "updated", "state_changed"]
    actions = ["force_execution"]
    search_fields = ["identity__username"]

    @admin.action(description="Force Execution")
    def force_execution(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("new")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PostInteraction)
class PostInteractionAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "type", "identity", "post"]
    list_filter = (IdentityLocalFilter, "type", "state")
    raw_id_fields = ["identity", "post"]

    def has_add_permission(self, request, obj=None):
        return False
