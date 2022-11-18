import re

from django.conf import settings as djsettings
from django.contrib import admin as djadmin
from django.urls import path, re_path
from django.views.static import serve

from activities.views import posts, search, timelines
from core import views as core
from stator import views as stator
from users.views import activitypub, admin, auth, identity, settings

urlpatterns = [
    path("", core.homepage),
    path("manifest.json", core.AppManifest.as_view()),
    # Activity views
    path("notifications/", timelines.Notifications.as_view(), name="notifications"),
    path("local/", timelines.Local.as_view(), name="local"),
    path("federated/", timelines.Federated.as_view(), name="federated"),
    path("search/", search.Search.as_view(), name="search"),
    path(
        "settings/",
        settings.SettingsRoot.as_view(),
        name="settings",
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
        "admin/",
        admin.AdminRoot.as_view(),
        name="admin",
    ),
    path(
        "admin/basic/",
        admin.BasicPage.as_view(),
        name="admin_basic",
    ),
    path(
        "admin/domains/",
        admin.DomainsPage.as_view(),
        name="admin_domains",
    ),
    path(
        "admin/domains/create/",
        admin.DomainCreatePage.as_view(),
        name="admin_domains_create",
    ),
    path(
        "admin/domains/<domain>/",
        admin.DomainEditPage.as_view(),
    ),
    path(
        "admin/domains/<domain>/delete/",
        admin.DomainDeletePage.as_view(),
    ),
    path(
        "admin/users/",
        admin.UsersPage.as_view(),
        name="admin_users",
    ),
    path(
        "admin/identities/",
        admin.IdentitiesPage.as_view(),
        name="admin_identities",
    ),
    # Identity views
    path("@<handle>/", identity.ViewIdentity.as_view()),
    path("@<handle>/actor/", activitypub.Actor.as_view()),
    path("@<handle>/actor/inbox/", activitypub.Inbox.as_view()),
    path("@<handle>/action/", identity.ActionIdentity.as_view()),
    # Posts
    path("compose/", posts.Compose.as_view(), name="compose"),
    path("@<handle>/posts/<int:post_id>/", posts.Individual.as_view()),
    path("@<handle>/posts/<int:post_id>/like/", posts.Like.as_view()),
    path("@<handle>/posts/<int:post_id>/unlike/", posts.Like.as_view(undo=True)),
    path("@<handle>/posts/<int:post_id>/boost/", posts.Boost.as_view()),
    path("@<handle>/posts/<int:post_id>/unboost/", posts.Boost.as_view(undo=True)),
    # Authentication
    path("auth/login/", auth.Login.as_view()),
    path("auth/logout/", auth.Logout.as_view()),
    # Identity selection
    path("@<handle>/activate/", identity.ActivateIdentity.as_view()),
    path("identity/select/", identity.SelectIdentity.as_view()),
    path("identity/create/", identity.CreateIdentity.as_view()),
    # Well-known endpoints
    path(".well-known/webfinger", activitypub.Webfinger.as_view()),
    path(".well-known/host-meta", activitypub.HostMeta.as_view()),
    # Task runner
    path(".stator/runner/", stator.RequestRunner.as_view()),
    # Django admin
    path("djadmin/", djadmin.site.urls),
    # Media files
    re_path(
        r"^%s(?P<path>.*)$" % re.escape(djsettings.MEDIA_URL.lstrip("/")),
        serve,
        kwargs={"document_root": djsettings.MEDIA_ROOT},
    ),
]
