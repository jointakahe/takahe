from django import forms
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView, View

from activities.models import (
    Post,
    PostInteraction,
    PostInteractionStates,
    TimelineEvent,
)
from core.models import Config
from users.decorators import identity_required
from users.shortcuts import by_handle_or_404


class Individual(TemplateView):

    template_name = "activities/post.html"

    def get_context_data(self, handle, post_id):
        identity = by_handle_or_404(self.request, handle, local=False)
        post = get_object_or_404(identity.posts, pk=post_id)
        return {
            "identity": identity,
            "post": post,
            "interactions": PostInteraction.get_post_interactions(
                [post],
                self.request.identity,
            ),
        }


@method_decorator(identity_required, name="dispatch")
class Like(View):
    """
    Adds/removes a like from the current identity to the post
    """

    undo = False

    def post(self, request, handle, post_id):
        identity = by_handle_or_404(self.request, handle, local=False)
        post = get_object_or_404(
            identity.posts.prefetch_related("attachments"), pk=post_id
        )
        if self.undo:
            # Undo any likes on the post
            for interaction in PostInteraction.objects.filter(
                type=PostInteraction.Types.like,
                identity=request.identity,
                post=post,
            ):
                interaction.transition_perform(PostInteractionStates.undone)
        else:
            # Make a like on this post if we didn't already
            PostInteraction.objects.get_or_create(
                type=PostInteraction.Types.like,
                identity=request.identity,
                post=post,
            )
        # Return either a redirect or a HTMX snippet
        if request.htmx:
            return render(
                request,
                "activities/_like.html",
                {
                    "post": post,
                    "interactions": {"like": set() if self.undo else {post.pk}},
                },
            )
        return redirect(post.urls.view)


@method_decorator(identity_required, name="dispatch")
class Boost(View):
    """
    Adds/removes a boost from the current identity to the post
    """

    undo = False

    def post(self, request, handle, post_id):
        identity = by_handle_or_404(self.request, handle, local=False)
        post = get_object_or_404(identity.posts, pk=post_id)
        if self.undo:
            # Undo any boosts on the post
            for interaction in PostInteraction.objects.filter(
                type=PostInteraction.Types.boost,
                identity=request.identity,
                post=post,
            ):
                interaction.transition_perform(PostInteractionStates.undone)
        else:
            # Make a boost on this post if we didn't already
            PostInteraction.objects.get_or_create(
                type=PostInteraction.Types.boost,
                identity=request.identity,
                post=post,
            )
        # Return either a redirect or a HTMX snippet
        if request.htmx:
            return render(
                request,
                "activities/_boost.html",
                {
                    "post": post,
                    "interactions": {"boost": set() if self.undo else {post.pk}},
                },
            )
        return redirect(post.urls.view)


@method_decorator(identity_required, name="dispatch")
class Compose(FormView):

    template_name = "activities/compose.html"

    class form_class(forms.Form):

        text = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "placeholder": "What's on your mind?",
                },
            )
        )
        visibility = forms.ChoiceField(
            choices=[
                (Post.Visibilities.public, "Public"),
                (Post.Visibilities.unlisted, "Unlisted"),
                (Post.Visibilities.followers, "Followers & Mentioned Only"),
                (Post.Visibilities.mentioned, "Mentioned Only"),
            ],
        )
        content_warning = forms.CharField(
            required=False,
            widget=forms.TextInput(
                attrs={
                    "placeholder": "Content Warning",
                },
            ),
            help_text="Optional - Post will be hidden behind this text until clicked",
        )

        def clean_text(self):
            text = self.cleaned_data.get("text")
            if not text:
                return text
            length = len(text)
            if length > Config.system.post_length:
                raise forms.ValidationError(
                    f"Maximum post length is {Config.system.post_length} characters (you have {length})"
                )
            return text

    def get_form_class(self):
        form = super().get_form_class()
        form.declared_fields["text"]
        return form

    def form_valid(self, form):
        post = Post.create_local(
            author=self.request.identity,
            content=form.cleaned_data["text"],
            summary=form.cleaned_data.get("content_warning"),
            visibility=form.cleaned_data["visibility"],
        )
        # Add their own timeline event for immediate visibility
        TimelineEvent.add_post(self.request.identity, post)
        return redirect("/")
