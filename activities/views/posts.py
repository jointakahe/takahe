from django import forms
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView, View

from activities.models import (
    Post,
    PostInteraction,
    PostInteractionStates,
    PostStates,
    TimelineEvent,
)
from core.html import html_to_plaintext
from core.ld import canonicalise
from core.models import Config
from users.decorators import identity_required
from users.shortcuts import by_handle_or_404


class Individual(TemplateView):

    template_name = "activities/post.html"

    def get(self, request, handle, post_id):
        self.identity = by_handle_or_404(self.request, handle, local=False)
        self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)
        # If they're coming in looking for JSON, they want the actor
        accept = request.META.get("HTTP_ACCEPT", "text/html").lower()
        if (
            "application/json" in accept
            or "application/ld" in accept
            or "application/activity" in accept
        ):
            # Return post JSON
            return self.serve_object()
        else:
            # Show normal page
            return super().get(request)

    def get_context_data(self):
        return {
            "identity": self.identity,
            "post": self.post_obj,
            "interactions": PostInteraction.get_post_interactions(
                [self.post_obj],
                self.request.identity,
            ),
            "replies": Post.objects.filter(
                models.Q(
                    visibility__in=[
                        Post.Visibilities.public,
                        Post.Visibilities.local_only,
                        Post.Visibilities.unlisted,
                    ]
                )
                | models.Q(
                    visibility=Post.Visibilities.followers,
                    author__inbound_follows__source=self.identity,
                )
                | models.Q(
                    visibility=Post.Visibilities.mentioned,
                    mentions=self.identity,
                ),
                in_reply_to=self.post_obj.object_uri,
            )
            .distinct()
            .order_by("published", "created"),
        }

    def serve_object(self):
        # If this not a local post, redirect to its canonical URI
        if not self.post_obj.local:
            return redirect(self.post_obj.object_uri)
        return JsonResponse(
            canonicalise(
                self.post_obj.to_ap(),
                include_security=True
            ),
            content_type='application/activity+json'
        )


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
class Delete(TemplateView):
    """
    Deletes a post
    """

    template_name = "activities/post_delete.html"

    def dispatch(self, request, handle, post_id):
        # Make sure the request identity owns the post!
        if handle != request.identity.handle:
            raise PermissionDenied("Post author is not requestor")
        self.identity = by_handle_or_404(self.request, handle, local=False)
        self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)
        return super().dispatch(request)

    def get_context_data(self):
        return {"post": self.post_obj}

    def post(self, request):
        self.post_obj.transition_perform(PostStates.deleted)
        return redirect("/")


@method_decorator(identity_required, name="dispatch")
class Compose(FormView):

    template_name = "activities/compose.html"

    class form_class(forms.Form):
        id = forms.IntegerField(
            required=False,
            widget=forms.HiddenInput(),
        )

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
                (Post.Visibilities.local_only, "Local Only"),
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
        if self.post_obj:
            initial.update(
                {
                    "id": self.post_obj.id,
                    "reply_to": self.reply_to.pk if self.reply_to else "",
                    "visibility": self.post_obj.visibility,
                    "text": html_to_plaintext(self.post_obj.content),
                    "content_warning": self.post_obj.summary,
                }
            )
        else:
            initial[
                "visibility"
            ] = self.request.identity.config_identity.default_post_visibility
            if self.reply_to:
                initial["reply_to"] = self.reply_to.pk
                initial["visibility"] = self.reply_to.visibility
                initial["text"] = f"@{self.reply_to.author.handle} "
        return initial

    def form_valid(self, form):
        post_id = form.cleaned_data.get("id")
        if post_id:
            post = get_object_or_404(self.request.identity.posts, pk=post_id)
            post.edit_local(
                content=form.cleaned_data["text"],
                summary=form.cleaned_data.get("content_warning"),
                visibility=form.cleaned_data["visibility"],
            )

            # Should there be a timeline event for edits?
            # E.g. "@user edited #123"

            post.transition_perform(PostStates.edited)
        else:
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

    def dispatch(self, request, handle=None, post_id=None, *args, **kwargs):
        self.post_obj = None
        if handle and post_id:
            # Make sure the request identity owns the post!
            if handle != request.identity.handle:
                raise PermissionDenied("Post author is not requestor")

            self.post_obj = get_object_or_404(request.identity.posts, pk=post_id)

        # Grab the reply-to post info now
        self.reply_to = None
        reply_to_id = request.POST.get("reply_to") or request.GET.get("reply_to")
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
