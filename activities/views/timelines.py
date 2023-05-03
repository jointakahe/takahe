from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import ListView, TemplateView

from activities.models import Hashtag, TimelineEvent
from activities.services import TimelineService
from core.decorators import cache_page
from users.models import Identity
from users.views.base import IdentityViewMixin


@method_decorator(login_required, name="dispatch")
class Home(TemplateView):
    """
    Homepage for logged-in users - shows identities primarily.
    """

    template_name = "activities/home.html"

    def get_context_data(self):
        return {
            "identities": Identity.objects.filter(
                users__pk=self.request.user.pk
            ).order_by("created"),
        }


@method_decorator(
    cache_page("cache_timeout_page_timeline", public_only=True), name="dispatch"
)
class Tag(ListView):
    template_name = "activities/tag.html"
    extra_context = {
        "current_page": "tag",
        "allows_refresh": True,
    }
    paginate_by = 25

    def get(self, request, hashtag, *args, **kwargs):
        tag = hashtag.lower().lstrip("#")
        if hashtag != tag:
            # SEO sanitize
            return redirect(f"/tags/{tag}/", permanent=True)
        self.hashtag = get_object_or_404(Hashtag.objects.public(), hashtag=tag)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return TimelineService(None).hashtag(self.hashtag)

    def get_context_data(self):
        context = super().get_context_data()
        context["hashtag"] = self.hashtag
        return context


class Notifications(IdentityViewMixin, ListView):
    template_name = "activities/notifications.html"
    extra_context = {
        "current_page": "notifications",
        "allows_refresh": True,
    }
    paginate_by = 25
    notification_types = {
        "followed": TimelineEvent.Types.followed,
        "boosted": TimelineEvent.Types.boosted,
        "mentioned": TimelineEvent.Types.mentioned,
        "liked": TimelineEvent.Types.liked,
    }

    def get_queryset(self):
        # Did they ask to change options?
        notification_options = self.request.session.get("notification_options", {})
        for type_name in self.notification_types:
            notification_options.setdefault(type_name, True)
            if self.request.GET.get(type_name) == "true":
                notification_options[type_name] = True
            elif self.request.GET.get(type_name) == "false":
                notification_options[type_name] = False
        self.request.session["notification_options"] = notification_options
        # Return appropriate events
        types = []
        for type_name, type in self.notification_types.items():
            if notification_options.get(type_name, True):
                types.append(type)
        return TimelineService(self.identity).notifications(types)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Collapse similar notifications into one
        events = []
        for event in context["page_obj"]:
            if (
                events
                and event.type
                in [
                    TimelineEvent.Types.liked,
                    TimelineEvent.Types.boosted,
                    TimelineEvent.Types.mentioned,
                ]
                and event.subject_post_id == events[-1].subject_post_id
            ):
                events[-1].collapsed = True
            events.append(event)
        # Retrieve what kinds of things to show
        context["events"] = events
        context["identity"] = self.identity
        context["notification_options"] = self.request.session["notification_options"]
        return context
