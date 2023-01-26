from asgiref.sync import async_to_sync
from django.contrib import admin
from django.db import models
from django.utils import formats
from django.utils.translation import gettext_lazy as _

from activities.admin import IdentityLocalFilter
from users.models import (
    Announcement,
    Block,
    Domain,
    Follow,
    Identity,
    InboxMessage,
    Invite,
    PasswordReset,
    Report,
    User,
    UserEvent,
)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = [
        "domain",
        "service_domain",
        "local",
        "blocked",
        "software",
        "user_count",
        "public",
    ]
    list_filter = ("local", "blocked")
    search_fields = ("domain", "service_domain")
    autocomplete_fields = ("users",)
    actions = [
        "force_outdated",
        "force_updated",
        "force_connection_issue",
        "fetch_nodeinfo",
    ]

    @admin.action(description="Force State: outdated")
    def force_outdated(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

    @admin.action(description="Force State: updated")
    def force_updated(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("updated")

    @admin.action(description="Force State: connection_issue")
    def force_connection_issue(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("connection_issue")

    @admin.action(description="Fetch nodeinfo")
    def fetch_nodeinfo(self, request, queryset):
        for instance in queryset:
            info = async_to_sync(instance.fetch_nodeinfo)()
            if info:
                instance.nodeinfo = info.dict()
                instance.save()

    @admin.display(description="Software")
    def software(self, instance):
        if instance.nodeinfo:
            software = instance.nodeinfo.get("software", {})
            name = software.get("name", "unknown")
            version = software.get("version", "unknown")
            return f"{name:.10} - {version:.10}"

        return "-"

    @admin.display(description="# Users")
    def user_count(self, instance):
        if instance.nodeinfo:
            usage = instance.nodeinfo.get("usage", {})
            total = usage.get("users", {}).get("total")
            if total:
                try:
                    return formats.number_format(
                        "%d" % (int(total)),
                        0,
                        use_l10n=True,
                        force_grouping=True,
                    )
                except ValueError:
                    pass
        return "-"


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "created", "last_seen", "admin", "moderator", "banned"]
    search_fields = ["email"]
    list_filter = ("admin", "moderator", "banned")


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ["id", "handle", "actor_uri", "state", "local"]
    list_filter = ("local", "state", "discoverable")
    autocomplete_fields = ["users"]
    actions = ["force_update"]
    readonly_fields = ["handle", "actor_json"]
    search_fields = ["search_handle", "search_service_handle", "name", "id"]

    def get_search_results(self, request, queryset, search_term):
        from django.db.models.functions import Concat

        queryset = queryset.annotate(
            search_handle=Concat("username", models.Value("@"), "domain_id"),
            search_service_handle=Concat(
                "username", models.Value("@"), "domain__service_domain"
            ),
        )
        return super().get_search_results(request, queryset, search_term)

    @admin.action(description="Force update")
    def force_update(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

    @admin.action(description="Mark as deleted")
    def delete(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("deleted")

    @admin.display(description="ActivityPub JSON")
    def actor_json(self, instance):
        return instance.to_ap()

    def has_add_permission(self, request, obj=None):
        return False


class LocalSourceFilter(IdentityLocalFilter):
    title = _("Local Source Identity")
    parameter_name = "srclocal"
    identity_field_name = "source"


class LocalTargetFilter(IdentityLocalFilter):
    title = _("Local Target Identity")
    parameter_name = "tgtlocal"
    identity_field_name = "target"


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "target", "state"]
    list_filter = [LocalSourceFilter, LocalTargetFilter, "state"]
    autocomplete_fields = ["source", "target"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "target", "mute", "state"]
    list_filter = [LocalSourceFilter, LocalTargetFilter, "state"]
    autocomplete_fields = ["source", "target"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "created"]
    autocomplete_fields = ["user"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InboxMessage)
class InboxMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "state",
        "state_changed",
        "message_type_full",
        "message_actor",
    ]
    list_filter = ("state",)
    search_fields = ["message"]
    actions = ["reset_state"]
    readonly_fields = ["state_changed"]

    @admin.action(description="Reset State")
    def reset_state(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("received")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ["id", "created", "token", "note"]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "created", "resolved", "type", "subject_identity"]


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["id", "published", "start", "end", "text"]
    autocomplete_fields = ["seen"]
