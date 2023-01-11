from django.utils.decorators import method_decorator
from django.views.generic import RedirectView

from users.decorators import admin_required
from users.views.admin.domains import (  # noqa
    DomainCreate,
    DomainDelete,
    DomainEdit,
    Domains,
)
from users.views.admin.emoji import (  # noqa
    EmojiCreate,
    EmojiDelete,
    EmojiEnable,
    EmojiRoot,
)
from users.views.admin.federation import FederationEdit, FederationRoot  # noqa
from users.views.admin.hashtags import HashtagEdit, HashtagEnable, Hashtags  # noqa
from users.views.admin.identities import IdentitiesRoot, IdentityEdit  # noqa
from users.views.admin.invites import InviteCreate, InvitesRoot, InviteView  # noqa
from users.views.admin.reports import ReportsRoot, ReportView  # noqa
from users.views.admin.settings import (  # noqa
    BasicSettings,
    PoliciesSettings,
    TuningSettings,
)
from users.views.admin.stator import Stator  # noqa
from users.views.admin.users import UserEdit, UsersRoot  # noqa


@method_decorator(admin_required, name="dispatch")
class AdminRoot(RedirectView):
    pattern_name = "admin_basic"
