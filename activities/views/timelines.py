from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import ListView, TemplateView

from activities.models import Hashtag, PostInteraction, TimelineEvent
from activities.services import TimelineService
from core.decorators import cache_page
from users.decorators import identity_required

from .compose import Compose


@method_decorator(identity_required, name="dispatch")
class Home(TemplateView):

    template_name = "activities/home.html"

    form_class = Compose.form_class

    def get_form(self, form_class=None):
        return self.form_class(request=self.request, **self.get_form_kwargs())

    def get_context_data(self):
        events = TimelineService(self.request.identity).home()
        paginator = Paginator(events, 25)
        page_number = self.request.GET.get("page")
        event_page = paginator.get_page(page_number)
        context = {
            "interactions": PostInteraction.get_event_interactions(
                event_page,
                self.request.identity,
            ),
            "current_page": "home",
            "allows_refresh": True,
            "page_obj": event_page,
            "form": self.form_class(request=self.request),
        }
        return context


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
        return TimelineService(self.request.identity).hashtag(self.hashtag)

    def get_context_data(self):
        context = super().get_context_data()
        context["hashtag"] = self.hashtag
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


@method_decorator(
    cache_page("cache_timeout_page_timeline", public_only=True), name="dispatch"
)
class Local(ListView):

    template_name = "activities/local.html"
    extra_context = {
        "current_page": "local",
        "allows_refresh": True,
    }
    paginate_by = 25

    def get_queryset(self):
        return TimelineService(self.request.identity).local()

    def get_context_data(self):
        context = super().get_context_data()
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


@method_decorator(identity_required, name="dispatch")
class Federated(ListView):

    template_name = "activities/federated.html"
    extra_context = {
        "current_page": "federated",
        "allows_refresh": True,
    }
    paginate_by = 25

    def get_queryset(self):
        return TimelineService(self.request.identity).federated()

    def get_context_data(self):
        context = super().get_context_data()
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"], self.request.identity
        )
        return context


@method_decorator(identity_required, name="dispatch")
class Notifications(ListView):

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
        return TimelineService(self.request.identity).notifications(types)

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
        context["notification_options"] = self.request.session["notification_options"]
        context["interactions"] = PostInteraction.get_event_interactions(
            context["page_obj"],
            self.request.identity,
        )
        return context
