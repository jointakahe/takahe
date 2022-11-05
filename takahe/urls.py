from django.contrib import admin
from django.urls import path

from core import views as core
from users.views import auth, identity

urlpatterns = [
    path("", core.homepage),
    # Authentication
    path("auth/login/", auth.Login.as_view()),
    path("auth/logout/", auth.Logout.as_view()),
    # Identity views
    path("@<handle>/", identity.ViewIdentity.as_view()),
    path("@<handle>/actor/", identity.Actor.as_view()),
    # Identity selection
    path("identity/select/", identity.SelectIdentity.as_view()),
    path("identity/create/", identity.CreateIdentity.as_view()),
    # Well-known endpoints
    path(".well-known/webfinger/", identity.Webfinger.as_view()),
    # Django admin
    path("djadmin/", admin.site.urls),
]
