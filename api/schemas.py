from typing import Literal, Optional, Union

from django.conf import settings
from hatchway import Field, Schema

from activities import models as activities_models
from api import models as api_models
from core.html import FediverseHtmlParser
from users import models as users_models
from users.services import IdentityService


class Application(Schema):
    id: str
    name: str
    website: str | None
    client_id: str
    client_secret: str
    redirect_uri: str = Field(alias="redirect_uris")
    vapid_key: str | None

    @classmethod
    def from_application(cls, application: api_models.Application) -> "Application":
        instance = cls.from_orm(application)
        instance.vapid_key = settings.SETUP.VAPID_PUBLIC_KEY
        return instance

    @classmethod
    def from_application_no_keys(
        cls, application: api_models.Application
    ) -> "Application":
        instance = cls.from_orm(application)
        instance.vapid_key = settings.SETUP.VAPID_PUBLIC_KEY
        instance.client_id = ""
        instance.client_secret = ""
        return instance


class CustomEmoji(Schema):
    shortcode: str
    url: str
    static_url: str
    visible_in_picker: bool
    category: str

    @classmethod
    def from_emoji(cls, emoji: activities_models.Emoji) -> "CustomEmoji":
        return cls(**emoji.to_mastodon_json())


class AccountField(Schema):
    name: str
    value: str
    verified_at: str | None


class Account(Schema):
    id: str
    username: str
    acct: str
    url: str
    display_name: str
    note: str
    avatar: str
    avatar_static: str
    header: str | None = Field(...)
    header_static: str | None = Field(...)
    locked: bool
    fields: list[AccountField]
    emojis: list[CustomEmoji]
    bot: bool
    group: bool
    discoverable: bool
    moved: Union[None, bool, "Account"]
    suspended: bool = False
    limited: bool = False
    created_at: str
    last_status_at: str | None = Field(...)
    statuses_count: int
    followers_count: int
    following_count: int
    source: dict | None

    @classmethod
    def from_identity(
        cls,
        identity: users_models.Identity,
        include_counts: bool = True,
        source=False,
    ) -> "Account":
        return cls(
            **identity.to_mastodon_json(include_counts=include_counts, source=source)
        )


class MediaAttachment(Schema):
    id: str
    type: Literal["unknown", "image", "gifv", "video", "audio"]
    url: str
    preview_url: str
    remote_url: str | None
    meta: dict
    description: str | None
    blurhash: str | None

    @classmethod
    def from_post_attachment(
        cls, attachment: activities_models.PostAttachment
    ) -> "MediaAttachment":
        return cls(**attachment.to_mastodon_json())


class PollOptions(Schema):
    title: str
    votes_count: int | None


class Poll(Schema):
    id: str
    expires_at: str | None
    expired: bool
    multiple: bool
    votes_count: int
    voters_count: int | None
    voted: bool
    own_votes: list[int]
    options: list[PollOptions]
    emojis: list[CustomEmoji]

    @classmethod
    def from_post(
        cls,
        post: activities_models.Post,
        identity: users_models.Identity | None = None,
    ) -> "Poll":
        return cls(**post.type_data.to_mastodon_json(post, identity=identity))


class StatusMention(Schema):
    id: str
    username: str
    url: str
    acct: str


class StatusTag(Schema):
    name: str
    url: str


class Status(Schema):
    id: str
    uri: str
    created_at: str
    account: Account
    content: str
    visibility: Literal["public", "unlisted", "private", "direct"]
    sensitive: bool
    spoiler_text: str
    media_attachments: list[MediaAttachment]
    mentions: list[StatusMention]
    tags: list[StatusTag]
    emojis: list[CustomEmoji]
    reblogs_count: int
    favourites_count: int
    replies_count: int
    url: str | None = Field(...)
    in_reply_to_id: str | None = Field(...)
    in_reply_to_account_id: str | None = Field(...)
    reblog: Optional["Status"] = Field(...)
    poll: Poll | None = Field(...)
    card: None = Field(...)
    language: None = Field(...)
    text: str | None = Field(...)
    edited_at: str | None
    favourited: bool = False
    reblogged: bool = False
    muted: bool = False
    bookmarked: bool = False
    pinned: bool = False

    @classmethod
    def from_post(
        cls,
        post: activities_models.Post,
        interactions: dict[str, set[str]] | None = None,
        bookmarks: set[str] | None = None,
        identity: users_models.Identity | None = None,
    ) -> "Status":
        return cls(
            **post.to_mastodon_json(
                interactions=interactions,
                bookmarks=bookmarks,
                identity=identity,
            )
        )

    @classmethod
    def map_from_post(
        cls,
        posts: list[activities_models.Post],
        identity: users_models.Identity,
    ) -> list["Status"]:
        interactions = activities_models.PostInteraction.get_post_interactions(
            posts, identity
        )
        bookmarks = users_models.Bookmark.for_identity(identity, posts)
        return [
            cls.from_post(
                post,
                interactions=interactions,
                bookmarks=bookmarks,
                identity=identity,
            )
            for post in posts
        ]

    @classmethod
    def from_timeline_event(
        cls,
        timeline_event: activities_models.TimelineEvent,
        interactions: dict[str, set[str]] | None = None,
        bookmarks: set[str] | None = None,
        identity: users_models.Identity | None = None,
    ) -> "Status":
        return cls(
            **timeline_event.to_mastodon_status_json(
                interactions=interactions, bookmarks=bookmarks, identity=identity
            )
        )

    @classmethod
    def map_from_timeline_event(
        cls,
        events: list[activities_models.TimelineEvent],
        identity: users_models.Identity,
    ) -> list["Status"]:
        interactions = activities_models.PostInteraction.get_event_interactions(
            events, identity
        )
        bookmarks = users_models.Bookmark.for_identity(
            identity, events, "subject_post_id"
        )
        return [
            cls.from_timeline_event(
                event, interactions=interactions, bookmarks=bookmarks, identity=identity
            )
            for event in events
        ]


class StatusSource(Schema):
    id: str
    text: str
    spoiler_text: str

    @classmethod
    def from_post(cls, post: activities_models.Post):
        return cls(
            id=post.id,
            text=FediverseHtmlParser(post.content).plain_text,
            spoiler_text=post.summary or "",
        )


class Conversation(Schema):
    id: str
    unread: bool
    accounts: list[Account]
    last_status: Status | None = Field(...)


class Notification(Schema):
    id: str
    type: Literal[
        "mention",
        "status",
        "reblog",
        "follow",
        "follow_request",
        "favourite",
        "poll",
        "update",
        "admin.sign_up",
        "admin.report",
    ]
    created_at: str
    account: Account
    status: Status | None

    @classmethod
    def from_timeline_event(
        cls,
        event: activities_models.TimelineEvent,
        interactions=None,
    ) -> "Notification":
        return cls(**event.to_mastodon_notification_json(interactions=interactions))


class Tag(Schema):
    name: str
    url: str
    history: list
    following: bool | None

    @classmethod
    def from_hashtag(
        cls,
        hashtag: activities_models.Hashtag,
        following: bool | None = None,
    ) -> "Tag":
        return cls(**hashtag.to_mastodon_json(following=following))


class FollowedTag(Tag):
    id: str

    @classmethod
    def from_follow(
        cls,
        follow: users_models.HashtagFollow,
    ) -> "FollowedTag":
        return cls(id=follow.id, **follow.hashtag.to_mastodon_json(following=True))

    @classmethod
    def map_from_follows(
        cls,
        hashtag_follows: list[users_models.HashtagFollow],
    ) -> list["Tag"]:
        return [cls.from_follow(follow) for follow in hashtag_follows]


class FeaturedTag(Schema):
    id: str
    name: str
    url: str
    statuses_count: int
    last_status_at: str


class Search(Schema):
    accounts: list[Account]
    statuses: list[Status]
    hashtags: list[Tag]


class Relationship(Schema):
    id: str
    following: bool
    followed_by: bool
    showing_reblogs: bool
    notifying: bool
    blocking: bool
    blocked_by: bool
    muting: bool
    muting_notifications: bool
    requested: bool
    domain_blocking: bool
    endorsed: bool
    note: str

    @classmethod
    def from_identity_pair(
        cls,
        identity: users_models.Identity,
        from_identity: users_models.Identity,
    ) -> "Relationship":
        return cls(
            **IdentityService(identity).mastodon_json_relationship(from_identity)
        )


class Context(Schema):
    ancestors: list[Status]
    descendants: list[Status]


class FamiliarFollowers(Schema):
    id: str
    accounts: list[Account]


class Announcement(Schema):
    id: str
    content: str
    starts_at: str | None = Field(...)
    ends_at: str | None = Field(...)
    all_day: bool
    published_at: str
    updated_at: str
    read: bool | None  # Only missing for anonymous responses
    mentions: list[Account]
    statuses: list[Status]
    tags: list[Tag]
    emojis: list[CustomEmoji]
    reactions: list

    @classmethod
    def from_announcement(
        cls,
        announcement: users_models.Announcement,
        user: users_models.User,
    ) -> "Announcement":
        return cls(**announcement.to_mastodon_json(user=user))


class List(Schema):
    id: str
    title: str
    replies_policy: Literal[
        "followed",
        "list",
        "none",
    ]


class Preferences(Schema):
    posting_default_visibility: Literal[
        "public",
        "unlisted",
        "private",
        "direct",
    ] = Field(alias="posting:default:visibility")
    posting_default_sensitive: bool = Field(alias="posting:default:sensitive")
    posting_default_language: str | None = Field(alias="posting:default:language")
    reading_expand_media: Literal[
        "default",
        "show_all",
        "hide_all",
    ] = Field(alias="reading:expand:media")
    reading_expand_spoilers: bool = Field(alias="reading:expand:spoilers")

    @classmethod
    def from_identity(
        cls,
        identity: users_models.Identity,
    ) -> "Preferences":
        visibility_mapping = {
            activities_models.Post.Visibilities.public: "public",
            activities_models.Post.Visibilities.unlisted: "unlisted",
            activities_models.Post.Visibilities.followers: "private",
            activities_models.Post.Visibilities.mentioned: "direct",
            activities_models.Post.Visibilities.local_only: "public",
        }
        return cls.parse_obj(
            {
                "posting:default:visibility": visibility_mapping[
                    identity.config_identity.default_post_visibility
                ],
                "posting:default:sensitive": False,
                "posting:default:language": None,
                "reading:expand:media": "default",
                "reading:expand:spoilers": identity.config_identity.expand_content_warnings,
            }
        )


class PushSubscriptionKeys(Schema):
    p256dh: str
    auth: str


class PushSubscriptionCreation(Schema):
    endpoint: str
    keys: PushSubscriptionKeys


class PushDataAlerts(Schema):
    mention: bool = False
    status: bool = False
    reblog: bool = False
    follow: bool = False
    follow_request: bool = False
    favourite: bool = False
    poll: bool = False
    update: bool = False
    admin_sign_up: bool = Field(False, alias="admin.sign_up")
    admin_report: bool = Field(False, alias="admin.report")


class PushData(Schema):
    alerts: PushDataAlerts
    policy: Literal["all", "followed", "follower", "none"] = "all"


class PushSubscription(Schema):
    id: str
    endpoint: str
    alerts: PushDataAlerts
    policy: str
    server_key: str

    @classmethod
    def from_token(
        cls,
        token: api_models.Token,
    ) -> Optional["PushSubscription"]:
        value = token.push_subscription
        if value:
            value["id"] = "1"
            value["server_key"] = settings.SETUP.VAPID_PUBLIC_KEY
            del value["keys"]
            return value
        else:
            return None
