from django.urls import path
from hatchway import methods

from api.views import (
    accounts,
    announcements,
    apps,
    emoji,
    filters,
    instance,
    media,
    notifications,
    polls,
    search,
    statuses,
    timelines,
    trends,
)

urlpatterns = [
    # Accounts
    path("v1/accounts/verify_credentials", accounts.verify_credentials),
    path("v1/accounts/update_credentials", accounts.update_credentials),
    path("v1/accounts/relationships", accounts.account_relationships),
    path("v1/accounts/familiar_followers", accounts.familiar_followers),
    path("v1/accounts/search", accounts.accounts_search),
    path("v1/accounts/lookup", accounts.lookup),
    path("v1/accounts/<id>", accounts.account),
    path("v1/accounts/<id>/statuses", accounts.account_statuses),
    path("v1/accounts/<id>/follow", accounts.account_follow),
    path("v1/accounts/<id>/unfollow", accounts.account_unfollow),
    path("v1/accounts/<id>/block", accounts.account_block),
    path("v1/accounts/<id>/unblock", accounts.account_unblock),
    path("v1/accounts/<id>/mute", accounts.account_mute),
    path("v1/accounts/<id>/unmute", accounts.account_unmute),
    path("v1/accounts/<id>/following", accounts.account_following),
    path("v1/accounts/<id>/followers", accounts.account_followers),
    # Announcements
    path("v1/announcements", announcements.announcement_list),
    path("v1/announcements/<pk>/dismiss", announcements.announcement_dismiss),
    # Apps
    path("v1/apps", apps.add_app),
    # Emoji
    path("v1/custom_emojis", emoji.emojis),
    # Filters
    path("v2/filters", filters.list_filters),
    path("v1/filters", filters.list_filters),
    # Instance
    path("v1/instance", instance.instance_info_v1),
    path("v2/instance", instance.instance_info_v2),
    # Media
    path("v1/media", media.upload_media),
    path("v2/media", media.upload_media),
    path("v1/media/<id>", methods(get=media.get_media, put=media.update_media)),
    path(
        "v1/statuses/<id>",
        methods(
            get=statuses.status,
            put=statuses.edit_status,
            delete=statuses.delete_status,
        ),
    ),
    path("v1/statuses/<id>/source", statuses.status_source),
    # Notifications
    path("v1/notifications", notifications.notifications),
    # Polls
    path("v1/polls/<id>", polls.get_poll),
    path("v1/polls/<id>/votes", polls.vote_poll),
    # Search
    path("v2/search", search.search),
    # Statuses
    path("v1/statuses", statuses.post_status),
    path("v1/statuses/<id>/context", statuses.status_context),
    path("v1/statuses/<id>/favourite", statuses.favourite_status),
    path("v1/statuses/<id>/unfavourite", statuses.unfavourite_status),
    path("v1/statuses/<id>/favourited_by", statuses.favourited_by),
    path("v1/statuses/<id>/reblog", statuses.reblog_status),
    path("v1/statuses/<id>/unreblog", statuses.unreblog_status),
    # Timelines
    path("v1/timelines/home", timelines.home),
    path("v1/timelines/public", timelines.public),
    path("v1/timelines/tag/<hashtag>", timelines.hashtag),
    path("v1/conversations", timelines.conversations),
    path("v1/favourites", timelines.favourites),
    # Trends
    path("v1/trends/tags", trends.trends_tags),
    path("v1/trends/statuses", trends.trends_statuses),
    path("v1/trends/links", trends.trends_links),
]
