from django.conf import settings as djsettings
from django.contrib import admin as djadmin
from django.urls import include, path, re_path

from activities.views import compose, debug, explore, follows, posts, search, timelines
from api.views import oauth
from core import views as core
from mediaproxy import views as mediaproxy
from stator import views as stator
from users.views import (
    activitypub,
    admin,
    announcements,
    auth,
    identity,
    report,
    settings,
)

urlpatterns = [
    path("", core.homepage),
    path("robots.txt", core.RobotsTxt.as_view()),
    path("manifest.json", core.AppManifest.as_view()),
    # Activity views
    path("notifications/", timelines.Notifications.as_view(), name="notifications"),
    path("local/", timelines.Local.as_view(), name="local"),
    path("federated/", timelines.Federated.as_view(), name="federated"),
    path("search/", search.Search.as_view(), name="search"),
    path("tags/<hashtag>/", timelines.Tag.as_view(), name="tag"),
    path("explore/", explore.Explore.as_view(), name="explore"),
    path("explore/tags/", explore.ExploreTag.as_view(), name="explore-tag"),
    path(
        "follows/",
        follows.Follows.as_view(),
        name="follows",
    ),
    # Settings views
    path(
        "settings/",
        settings.SettingsRoot.as_view(),
        name="settings",
    ),
    path(
        "settings/security/",
        settings.SecurityPage.as_view(),
        name="settings_security",
    ),
    path(
        "settings/profile/",
        settings.ProfilePage.as_view(),
        name="settings_profile",
    ),
    path(
        "settings/interface/",
        settings.InterfacePage.as_view(),
        name="settings_interface",
    ),
    path(
        "settings/import_export/",
        settings.ImportExportPage.as_view(),
        name="settings_import_export",
    ),
    path(
        "settings/import_export/following.csv",
        settings.CsvFollowing.as_view(),
        name="settings_export_following_csv",
    ),
    path(
        "settings/import_export/followers.csv",
        settings.CsvFollowers.as_view(),
        name="settings_export_followers_csv",
    ),
    path(
        "admin/",
        admin.AdminRoot.as_view(),
        name="admin",
    ),
    path(
        "admin/basic/",
        admin.BasicSettings.as_view(),
        name="admin_basic",
    ),
    path(
        "admin/tuning/",
        admin.TuningSettings.as_view(),
        name="admin_tuning",
    ),
    path(
        "admin/policies/",
        admin.PoliciesSettings.as_view(),
        name="admin_policies",
    ),
    path(
        "admin/domains/",
        admin.Domains.as_view(),
        name="admin_domains",
    ),
    path(
        "admin/domains/create/",
        admin.DomainCreate.as_view(),
        name="admin_domains_create",
    ),
    path(
        "admin/domains/<domain>/",
        admin.DomainEdit.as_view(),
    ),
    path(
        "admin/domains/<domain>/delete/",
        admin.DomainDelete.as_view(),
    ),
    path(
        "admin/federation/",
        admin.FederationRoot.as_view(),
        name="admin_federation",
    ),
    path(
        "admin/federation/<domain>/",
        admin.FederationEdit.as_view(),
        name="admin_federation_edit",
    ),
    path(
        "admin/users/",
        admin.UsersRoot.as_view(),
        name="admin_users",
    ),
    path(
        "admin/users/<id>/",
        admin.UserEdit.as_view(),
        name="admin_user_edit",
    ),
    path(
        "admin/identities/",
        admin.IdentitiesRoot.as_view(),
        name="admin_identities",
    ),
    path(
        "admin/identities/<id>/",
        admin.IdentityEdit.as_view(),
        name="admin_identity_edit",
    ),
    path(
        "admin/reports/",
        admin.ReportsRoot.as_view(),
        name="admin_reports",
    ),
    path(
        "admin/reports/<id>/",
        admin.ReportView.as_view(),
        name="admin_report_view",
    ),
    path(
        "admin/invites/",
        admin.InvitesRoot.as_view(),
        name="admin_invites",
    ),
    path(
        "admin/invites/create/",
        admin.InviteCreate.as_view(),
        name="admin_invite_create",
    ),
    path(
        "admin/invites/<id>/",
        admin.InviteView.as_view(),
        name="admin_invite_view",
    ),
    path(
        "admin/hashtags/",
        admin.Hashtags.as_view(),
        name="admin_hashtags",
    ),
    path(
        "admin/hashtags/<hashtag>/",
        admin.HashtagEdit.as_view(),
    ),
    path("admin/hashtags/<hashtag>/enable/", admin.HashtagEnable.as_view()),
    path(
        "admin/hashtags/<hashtag>/disable/", admin.HashtagEnable.as_view(enable=False)
    ),
    path(
        "admin/emoji/",
        admin.EmojiRoot.as_view(),
        name="admin_emoji",
    ),
    path(
        "admin/emoji/create/",
        admin.EmojiCreate.as_view(),
        name="admin_emoji_create",
    ),
    path("admin/emoji/<pk>/enable/", admin.EmojiEnable.as_view()),
    path("admin/emoji/<pk>/disable/", admin.EmojiEnable.as_view(enable=False)),
    path("admin/emoji/<pk>/delete/", admin.EmojiDelete.as_view()),
    path("admin/emoji/<pk>/copy/", admin.EmojiCopyLocal.as_view()),
    path(
        "admin/announcements/",
        admin.AnnouncementsRoot.as_view(),
        name="admin_announcements",
    ),
    path(
        "admin/announcements/create/",
        admin.AnnouncementCreate.as_view(),
        name="admin_announcement_create",
    ),
    path(
        "admin/announcements/<pk>/",
        admin.AnnouncementEdit.as_view(),
    ),
    path(
        "admin/announcements/<pk>/delete/",
        admin.AnnouncementDelete.as_view(),
    ),
    path(
        "admin/announcements/<pk>/publish/",
        admin.AnnouncementPublish.as_view(),
    ),
    path(
        "admin/announcements/<pk>/unpublish/",
        admin.AnnouncementUnpublish.as_view(),
    ),
    path(
        "admin/stator/",
        admin.Stator.as_view(),
        name="admin_stator",
    ),
    # Identity views
    path("@<handle>/", identity.ViewIdentity.as_view()),
    path("@<handle>/inbox/", activitypub.Inbox.as_view()),
    path("@<handle>/outbox/", activitypub.Outbox.as_view()),
    path("@<handle>/action/", identity.ActionIdentity.as_view()),
    path("@<handle>/rss/", identity.IdentityFeed()),
    path("@<handle>/report/", report.SubmitReport.as_view()),
    path("@<handle>/following/", identity.IdentityFollows.as_view(inbound=False)),
    path("@<handle>/followers/", identity.IdentityFollows.as_view(inbound=True)),
    # Posts
    path("compose/", compose.Compose.as_view(), name="compose"),
    path(
        "compose/image_upload/",
        compose.ImageUpload.as_view(),
        name="compose_image_upload",
    ),
    path("@<handle>/posts/<int:post_id>/", posts.Individual.as_view()),
    path("@<handle>/posts/<int:post_id>/like/", posts.Like.as_view()),
    path("@<handle>/posts/<int:post_id>/unlike/", posts.Like.as_view(undo=True)),
    path("@<handle>/posts/<int:post_id>/boost/", posts.Boost.as_view()),
    path("@<handle>/posts/<int:post_id>/unboost/", posts.Boost.as_view(undo=True)),
    path("@<handle>/posts/<int:post_id>/bookmark/", posts.Bookmark.as_view()),
    path(
        "@<handle>/posts/<int:post_id>/unbookmark/", posts.Bookmark.as_view(undo=True)
    ),
    path("@<handle>/posts/<int:post_id>/delete/", posts.Delete.as_view()),
    path("@<handle>/posts/<int:post_id>/report/", report.SubmitReport.as_view()),
    path("@<handle>/posts/<int:post_id>/edit/", compose.Compose.as_view()),
    # Authentication
    path("auth/login/", auth.Login.as_view(), name="login"),
    path("auth/logout/", auth.Logout.as_view(), name="logout"),
    path("auth/signup/", auth.Signup.as_view(), name="signup"),
    path("auth/signup/<token>/", auth.Signup.as_view(), name="signup"),
    path("auth/reset/", auth.TriggerReset.as_view(), name="trigger_reset"),
    path("auth/reset/<token>/", auth.PerformReset.as_view(), name="password_reset"),
    # Identity selection
    path("@<handle>/activate/", identity.ActivateIdentity.as_view()),
    path("identity/select/", identity.SelectIdentity.as_view(), name="identity_select"),
    path("identity/create/", identity.CreateIdentity.as_view(), name="identity_create"),
    # Flat pages
    path("about/", core.About.as_view(), name="about"),
    path(
        "pages/privacy/",
        core.FlatPage.as_view(title="Privacy Policy", config_option="policy_privacy"),
        name="privacy",
    ),
    path(
        "pages/terms/",
        core.FlatPage.as_view(title="Terms of Service", config_option="policy_terms"),
        name="terms",
    ),
    path(
        "pages/rules/",
        core.FlatPage.as_view(title="Server Rules", config_option="policy_rules"),
        name="rules",
    ),
    # Annoucements
    path("announcements/<id>/dismiss/", announcements.AnnouncementDismiss.as_view()),
    # Debug aids
    path("debug/json/", debug.JsonViewer.as_view()),
    path("debug/404/", debug.NotFound.as_view()),
    path("debug/500/", debug.ServerError.as_view()),
    path("debug/oauth_authorize/", debug.OauthAuthorize.as_view()),
    # Media/image proxy
    re_path(
        "^proxy/identity_icon/(?P<identity_id>[^/]+)/((?P<image_hash>[^/]+))?$",
        mediaproxy.IdentityIconCacheView.as_view(),
        name="proxy_identity_icon",
    ),
    re_path(
        "^proxy/identity_image/(?P<identity_id>[^/]+)/((?P<image_hash>[^/]+))?$",
        mediaproxy.IdentityImageCacheView.as_view(),
        name="proxy_identity_image",
    ),
    re_path(
        "^proxy/post_attachment/(?P<attachment_id>[^/]+)/((?P<image_hash>[^/]+))?$",
        mediaproxy.PostAttachmentCacheView.as_view(),
        name="proxy_post_attachment",
    ),
    re_path(
        "^proxy/emoji/(?P<emoji_id>[^/]+)/((?P<image_hash>[^/]+))?$",
        mediaproxy.EmojiCacheView.as_view(),
        name="proxy_emoji",
    ),
    # Well-known endpoints and system actor
    path(".well-known/webfinger", activitypub.Webfinger.as_view()),
    path(".well-known/host-meta", activitypub.HostMeta.as_view()),
    path(".well-known/nodeinfo", activitypub.NodeInfo.as_view()),
    path("nodeinfo/2.0/", activitypub.NodeInfo2.as_view()),
    path("actor/", activitypub.SystemActorView.as_view()),
    path("actor/inbox/", activitypub.Inbox.as_view()),
    path("actor/outbox/", activitypub.EmptyOutbox.as_view()),
    path("inbox/", activitypub.Inbox.as_view(), name="shared_inbox"),
    # API/Oauth
    path("api/", include("api.urls")),
    path("oauth/authorize", oauth.AuthorizationView.as_view()),
    path("oauth/token", oauth.TokenView.as_view()),
    path("oauth/revoke", oauth.RevokeTokenView.as_view()),
    # Stator
    path(".stator/", stator.RequestRunner.as_view()),
    # Django admin
    path("djadmin/", djadmin.site.urls),
    # Media files
    re_path(
        r"^media/(?P<path>.*)$",
        core.custom_static_serve,
        kwargs={"document_root": djsettings.MEDIA_ROOT},
    ),
]

# Debug toolbar
if djsettings.DEBUG:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
