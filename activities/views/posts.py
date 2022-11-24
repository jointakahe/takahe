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
            label=Config.lazy_system_value("content_warning_text"),
            widget=forms.TextInput(
                attrs={
                    "placeholder": Config.lazy_system_value("content_warning_text"),
                },
            ),
            help_text="Optional - Post will be hidden behind this text until clicked",
        )
        reply_to = forms.CharField(widget=forms.HiddenInput(), required=False)

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

    def get_initial(self):
        initial = super().get_initial()
        if self.reply_to:
            initial["reply_to"] = self.reply_to.pk
            initial["visibility"] = Post.Visibilities.unlisted
            initial["text"] = f"@{self.reply_to.author.handle} "
        return initial

    def form_valid(self, form):
        post = Post.create_local(
            author=self.request.identity,
            content=form.cleaned_data["text"],
            summary=form.cleaned_data.get("content_warning"),
            visibility=form.cleaned_data["visibility"],
            reply_to=self.reply_to,
        )
        # Add their own timeline event for immediate visibility
        TimelineEvent.add_post(self.request.identity, post)
        return redirect("/")

    def dispatch(self, request, *args, **kwargs):
        # Grab the reply-to post info now
        self.reply_to = None
        reply_to_id = self.request.POST.get("reply_to") or self.request.GET.get(
            "reply_to"
        )
        if reply_to_id:
            try:
                self.reply_to = Post.objects.get(pk=reply_to_id)
            except Post.DoesNotExist:
                pass
        # Keep going with normal rendering
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reply_to"] = self.reply_to
        return context
