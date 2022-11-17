from django.contrib import admin
from django.urls import path

from activities.views import posts, timelines
from core import views as core
from stator import views as stator
from users.views import activitypub, auth, identity, settings_identity, settings_system

urlpatterns = [
    path("", core.homepage),
    path("manifest.json", core.AppManifest.as_view()),
    # Activity views
    path("notifications/", timelines.Notifications.as_view()),
    path("local/", timelines.Local.as_view()),
    path("federated/", timelines.Federated.as_view()),
    path("settings/", settings_identity.IdentitySettingsRoot.as_view()),
    path("settings/interface/", settings_identity.InterfacePage.as_view()),
    path("settings/system/", settings_system.SystemSettingsRoot.as_view()),
    path("settings/system/basic/", settings_system.BasicPage.as_view()),
    # Identity views
    path("@<handle>/", identity.ViewIdentity.as_view()),
    path("@<handle>/actor/", activitypub.Actor.as_view()),
    path("@<handle>/actor/inbox/", activitypub.Inbox.as_view()),
    path("@<handle>/action/", identity.ActionIdentity.as_view()),
    # Posts
    path("compose/", posts.Compose.as_view()),
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
    path("djadmin/", admin.site.urls),
]
