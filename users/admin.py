from django.contrib import admin

from users.models import Domain, Follow, Identity, User, UserEvent


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


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ["id", "source", "target", "state"]
