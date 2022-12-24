from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _

from activities.admin import IdentityLocalFilter
from users.models import (
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
    list_display = ["domain", "service_domain", "local", "blocked", "public"]
    list_filter = ("local", "blocked")
    search_fields = ("domain", "service_domain")


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
    raw_id_fields = ["users"]
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

    @admin.action(description="Force Update")
    def force_update(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

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
    raw_id_fields = ["source", "target"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PasswordReset)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "created"]
    raw_id_fields = ["user"]

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
