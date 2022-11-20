from django import forms
from django.shortcuts import redirect
from django.template.defaultfilters import linebreaks_filter
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from activities.models import Post, PostInteraction, TimelineEvent
from core.models import Config
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class Home(FormView):

    template_name = "activities/home.html"

    class form_class(forms.Form):
        text = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "placeholder": "What's on your mind?",
                },
            )
        )
        content_warning = forms.CharField(
            required=False,
            label=Config.lazy_system_value("content_warning_text"),
            widget=forms.TextInput(
                attrs={
                    "class": "hidden",
                    "placeholder": Config.lazy_system_value("content_warning_text"),
                },
            ),
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["events"] = list(
            TimelineEvent.objects.filter(
                identity=self.request.identity,
                type__in=[TimelineEvent.Types.post, TimelineEvent.Types.boost],
            )
            .select_related("subject_post", "subject_post__author")
            .prefetch_related("subject_post__attachments")
            .order_by("-created")[:50]
        )
        context["interactions"] = PostInteraction.get_event_interactions(
            context["events"], self.request.identity
        )
        context["current_page"] = "home"
        return context

    def form_valid(self, form):
        Post.create_local(
            author=self.request.identity,
            content=linebreaks_filter(form.cleaned_data["text"]),
            summary=form.cleaned_data.get("content_warning"),
        )
        return redirect(".")


class Local(TemplateView):

    template_name = "activities/local.html"

    def get_context_data(self):
        context = super().get_context_data()
        context["posts"] = (
            Post.objects.filter(visibility=Post.Visibilities.public, author__local=True)
            .select_related("author")
            .prefetch_related("attachments")
            .order_by("-created")[:50]
        )
        context["current_page"] = "local"
        return context


@method_decorator(identity_required, name="dispatch")
class Federated(TemplateView):

    template_name = "activities/federated.html"

    def get_context_data(self):
        context = super().get_context_data()
        context["posts"] = (
            Post.objects.filter(visibility=Post.Visibilities.public)
            .select_related("author")
            .prefetch_related("attachments")
            .order_by("-created")[:50]
        )
        context["current_page"] = "federated"
        return context


@method_decorator(identity_required, name="dispatch")
class Notifications(TemplateView):

    template_name = "activities/notifications.html"

    def get_context_data(self):
        context = super().get_context_data()
        context["events"] = (
            TimelineEvent.objects.filter(
                identity=self.request.identity,
                type__in=[
                    TimelineEvent.Types.mentioned,
                    TimelineEvent.Types.boosted,
                    TimelineEvent.Types.liked,
                    TimelineEvent.Types.followed,
                ],
            )
            .order_by("-created")[:50]
            .select_related("subject_post", "subject_post__author", "subject_identity")
        )
        context["current_page"] = "notifications"
        return context
