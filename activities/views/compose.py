from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from activities.models import (
    Post,
    PostAttachment,
    PostAttachmentStates,
    PostStates,
    TimelineEvent,
)
from core.files import blurhash_image, resize_image
from core.html import FediverseHtmlParser
from core.models import Config
from users.shortcuts import by_handle_for_user_or_404
from django.contrib.auth.decorators import login_required


@method_decorator(login_required, name="dispatch")
class Compose(FormView):
    template_name = "activities/compose.html"

    class form_class(forms.Form):
        text = forms.CharField(
            widget=forms.Textarea(
                attrs={
                    "autofocus": "autofocus",
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

        def __init__(self, identity, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.identity = identity
            self.fields["text"].widget.attrs[
                "_"
            ] = rf"""
                init
                    -- Move cursor to the end of existing text
                    set my.selectionStart to my.value.length
                end

                on load or input
                -- Unicode-aware counting to match Python
                -- <LF> will be normalized as <CR><LF> in Django
                set characters to Array.from(my.value.replaceAll('\n','\r\n').trim()).length
                put {Config.system.post_length} - characters into #character-counter

                if characters > {Config.system.post_length} then
                    set #character-counter's style.color to 'var(--color-text-error)'
                    add [@disabled=] to #post-button
                else
                    set #character-counter's style.color to ''
                    remove @disabled from #post-button
                end
            """

        def clean_text(self):
            text = self.cleaned_data.get("text")
            # Check minimum interval
            last_post = self.identity.posts.order_by("-created").first()
            if (
                last_post
                and (timezone.now() - last_post.created).total_seconds()
                < Config.system.post_minimum_interval
            ):
                raise forms.ValidationError(
                    f"You must wait at least {Config.system.post_minimum_interval} seconds between posts"
                )
            if not text:
                return text
            # Check post length
            length = len(text)
            if length > Config.system.post_length:
                raise forms.ValidationError(
                    f"Maximum post length is {Config.system.post_length} characters (you have {length})"
                )
            return text

    def get_form(self, form_class=None):
        return self.form_class(identity=self.identity, **self.get_form_kwargs())

    def get_initial(self):
        initial = super().get_initial()
        if self.post_obj:
            initial.update(
                {
                    "reply_to": self.reply_to.pk if self.reply_to else "",
                    "visibility": self.post_obj.visibility,
                    "text": FediverseHtmlParser(self.post_obj.content).plain_text,
                    "content_warning": self.post_obj.summary,
                }
            )
        else:
            initial[
                "visibility"
            ] = self.identity.config_identity.default_post_visibility
            if self.reply_to:
                initial["reply_to"] = self.reply_to.pk
                initial["visibility"] = self.reply_to.visibility
                initial["content_warning"] = self.reply_to.summary
                # Build a set of mentions for the content to start as
                mentioned = {self.reply_to.author}
                mentioned.update(self.reply_to.mentions.all())
                mentioned.discard(self.identity)
                initial["text"] = "".join(
                    f"@{identity.handle} "
                    for identity in mentioned
                    if identity.username
                )
        return initial

    def form_valid(self, form):
        # Gather any attachment objects now, they're not in the form proper
        attachments = []
        if "attachment" in self.request.POST:
            attachments = PostAttachment.objects.filter(
                pk__in=self.request.POST.getlist("attachment", [])
            )
        # Dispatch based on edit or not
        if self.post_obj:
            self.post_obj.edit_local(
                content=form.cleaned_data["text"],
                summary=form.cleaned_data.get("content_warning"),
                visibility=form.cleaned_data["visibility"],
                attachments=attachments,
            )
            self.post_obj.transition_perform(PostStates.edited)
        else:
            post = Post.create_local(
                author=self.identity,
                content=form.cleaned_data["text"],
                summary=form.cleaned_data.get("content_warning"),
                visibility=form.cleaned_data["visibility"],
                reply_to=self.reply_to,
                attachments=attachments,
            )
            # Add their own timeline event for immediate visibility
            TimelineEvent.add_post(self.identity, post)
        return redirect(self.identity.urls.view)

    def dispatch(self, request, handle=None, post_id=None, *args, **kwargs):
        self.identity = by_handle_for_user_or_404(self.request, handle)
        self.post_obj = None
        if handle and post_id:
            self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)

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
        context["identity"] = self.identity
        context["section"] = "compose"
        if self.post_obj:
            context["post"] = self.post_obj
        return context
