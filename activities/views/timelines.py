from django import forms
from django.shortcuts import redirect
from django.template.defaultfilters import linebreaks_filter
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from activities.models import Post, TimelineEvent
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
            widget=forms.TextInput(
                attrs={
                    "placeholder": "Content Warning",
                    "class": "hidden",
                },
            ),
        )

    def get_context_data(self):
        context = super().get_context_data()
        context["timeline_posts"] = [
            te.subject_post
            for te in TimelineEvent.objects.filter(
                identity=self.request.identity,
                type=TimelineEvent.Types.post,
            )
            .select_related("subject_post", "subject_post__author")
            .order_by("-created")[:100]
        ]
        context["current_page"] = "home"
        return context

    def form_valid(self, form):
        Post.create_local(
            author=self.request.identity,
            content=linebreaks_filter(form.cleaned_data["text"]),
            summary=form.cleaned_data.get("content_warning"),
        )
        return redirect(".")


@method_decorator(identity_required, name="dispatch")
class Federated(TemplateView):

    template_name = "activities/federated.html"

    def get_context_data(self):
        context = super().get_context_data()
        context["timeline_posts"] = (
            Post.objects.filter(visibility=Post.Visibilities.public)
            .select_related("author")
            .order_by("-created")[:100]
        )
        context["current_page"] = "federated"
        return context
