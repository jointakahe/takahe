from django.contrib import admin

from users.models import Domain, Follow, Identity, InboxMessage, User, UserEvent


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ["domain", "service_domain", "local", "blocked", "public"]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    pass


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ["id", "handle", "actor_uri", "state", "local"]
    raw_id_fields = ["users"]
    actions = ["force_update"]
    readonly_fields = ["actor_json"]

    @admin.action(description="Force Update")
    def force_update(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("outdated")

    @admin.display(description="ActivityPub JSON")
    def actor_json(self, instance):
        return instance.to_ap()


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "target", "state"]
    raw_id_fields = ["source", "target"]


@admin.register(InboxMessage)
class InboxMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "state", "state_attempted", "message_type", "message_actor"]
    actions = ["reset_state"]

    @admin.action(description="Reset State")
    def reset_state(self, request, queryset):
        for instance in queryset:
            instance.transition_perform("received")
