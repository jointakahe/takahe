from django.contrib import admin

from users.models import Identity, User, UserEvent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    pass


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):

    list_display = ["id", "handle", "name", "local"]
