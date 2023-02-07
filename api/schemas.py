from typing import Literal, Optional, Union

from activities import models as activities_models
from hatchway import Field, Schema
from users import models as users_models
from users.services import IdentityService


class Application(Schema):
    id: str
    name: str
    website: str | None
    client_id: str
    client_secret: str
    redirect_uri: str = Field(alias="redirect_uris")


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
    poll: None = Field(...)
    card: None = Field(...)
    language: None = Field(...)
    text: str | None = Field(...)
    edited_at: str | None
    favourited: bool | None
    reblogged: bool | None
    muted: bool | None
    bookmarked: bool | None
    pinned: bool | None

    @classmethod
    def from_post(
        cls,
        post: activities_models.Post,
        interactions: dict[str, set[str]] | None = None,
    ) -> "Status":
        return cls(**post.to_mastodon_json(interactions=interactions))

    @classmethod
    def map_from_post(
        cls,
        posts: list[activities_models.Post],
        identity: users_models.Identity,
    ) -> list["Status"]:
        interactions = activities_models.PostInteraction.get_post_interactions(
            posts, identity
        )
        return [cls.from_post(post, interactions=interactions) for post in posts]

    @classmethod
    def from_timeline_event(
        cls,
        timeline_event: activities_models.TimelineEvent,
        interactions: dict[str, set[str]] | None = None,
    ) -> "Status":
        return cls(**timeline_event.to_mastodon_status_json(interactions=interactions))

    @classmethod
    def map_from_timeline_event(
        cls,
        events: list[activities_models.TimelineEvent],
        identity: users_models.Identity,
    ) -> list["Status"]:
        interactions = activities_models.PostInteraction.get_event_interactions(
            events, identity
        )
        return [
            cls.from_timeline_event(event, interactions=interactions)
            for event in events
        ]


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
    ) -> "Notification":
        return cls(**event.to_mastodon_notification_json())


class Tag(Schema):
    name: str
    url: str
    history: dict

    @classmethod
    def from_hashtag(
        cls,
        hashtag: activities_models.Hashtag,
    ) -> "Tag":
        return cls(**hashtag.to_mastodon_json())


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
