from django.contrib import admin
from django.db import models
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

    actions = ["force_execution", "approve_emoji", "reject_emoji", "copy_to_local"]

    def delete_queryset(self, request, queryset):
        for instance in queryset:
            # individual deletes to ensure file is deleted
            instance.delete()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)

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

    @admin.action(description="Copy Emoji to Local")
    def copy_to_local(self, request, queryset):
        emojis = {}
        for instance in queryset:
            emoji = instance.copy_to_local(save=False)
            if emoji:
                emojis[emoji.shortcode] = emoji

        Emoji.objects.bulk_create(emojis.values(), batch_size=50, ignore_conflicts=True)
        Emoji.locals = Emoji.load_locals()


@admin.register(PostAttachment)
class PostAttachmentAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "state", "created"]
    list_filter = ["state", "mimetype"]
    search_fields = ["name", "remote_url", "search_handle", "search_service_handle"]
    raw_id_fields = ["post"]

    actions = ["guess_mimetypes"]

    def get_search_results(self, request, queryset, search_term):
        from django.db.models.functions import Concat

        queryset = queryset.annotate(
            search_handle=Concat(
                "post__author__username", models.Value("@"), "post__author__domain_id"
            ),
            search_service_handle=Concat(
                "post__author__username",
                models.Value("@"),
                "post__author__domain__service_domain",
            ),
        )
        return super().get_search_results(request, queryset, search_term)

    @admin.action(description="Update mimetype based upon filename")
    def guess_mimetypes(self, request, queryset):
        import mimetypes

        for instance in queryset:
            if instance.remote_url:
                mimetype, _ = mimetypes.guess_type(instance.remote_url)
                if not mimetype:
                    mimetype = "application/octet-stream"
                instance.mimetype = mimetype
                instance.save()


class PostAttachmentInline(admin.StackedInline):
    model = PostAttachment
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "type", "author", "state", "created"]
    list_filter = ("type", "local", "visibility", "state", "created")
    raw_id_fields = ["emojis"]
    autocomplete_fields = ["to", "mentions", "author"]
    search_fields = ["content", "search_handle", "search_service_handle"]
    inlines = [PostAttachmentInline]
    readonly_fields = ["created", "updated", "state_changed", "object_json"]

    def get_search_results(self, request, queryset, search_term):
        from django.db.models.functions import Concat

        queryset = queryset.annotate(
            search_handle=Concat(
                "author__username", models.Value("@"), "author__domain_id"
            ),
            search_service_handle=Concat(
                "author__username", models.Value("@"), "author__domain__service_domain"
            ),
        )
        return super().get_search_results(request, queryset, search_term)

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
    autocomplete_fields = ["identity"]
    raw_id_fields = [
        "subject_post",
        "subject_identity",
        "subject_post_interaction",
    ]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FanOut)
class FanOutAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "created", "state_next_attempt", "type", "identity"]
    list_filter = (IdentityLocalFilter, "type", "state")
    raw_id_fields = ["subject_post", "subject_post_interaction"]
    autocomplete_fields = ["identity"]
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
    list_display = ["id", "state", "state_next_attempt", "type", "identity", "post"]
    list_filter = (IdentityLocalFilter, "type", "state")
    raw_id_fields = ["post"]
    autocomplete_fields = ["identity"]

    def has_add_permission(self, request, obj=None):
        return False
