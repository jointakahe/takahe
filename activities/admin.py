from django.contrib import admin

from activities.models import Post, TimelineEvent


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "author", "created"]
    raw_id_fields = ["to", "mentions"]


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ["id", "identity", "created", "type"]
    raw_id_fields = ["identity", "subject_post", "subject_identity"]
