from django import forms
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
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
from core.html import html_to_plaintext
from core.models import Config
from users.decorators import identity_required


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
                if self.reply_to.visibility == Post.Visibilities.public:
                    initial["visibility"] = Post.Visibilities.unlisted
                else:
                    initial["visibility"] = self.reply_to.visibility
                initial["text"] = f"@{self.reply_to.author.handle} "
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
                author=self.request.identity,
                content=form.cleaned_data["text"],
                summary=form.cleaned_data.get("content_warning"),
                visibility=form.cleaned_data["visibility"],
                reply_to=self.reply_to,
                attachments=attachments,
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
        if self.post_obj:
            context["post"] = self.post_obj
        return context


@method_decorator(identity_required, name="dispatch")
class ImageUpload(FormView):
    """
    Handles image upload - returns a new input type hidden to embed in
    the main form that references an orphaned PostAttachment
    """

    template_name = "activities/_image_upload.html"

    class form_class(forms.Form):
        image = forms.ImageField()
        description = forms.CharField(required=False)

    def form_valid(self, form):
        # Make a PostAttachment
        thumbnail_file = resize_image(form.cleaned_data["image"], size=(400, 225))
        attachment = PostAttachment.objects.create(
            blurhash=blurhash_image(thumbnail_file),
            mimetype=form.cleaned_data["image"].image.get_format_mimetype(),
            width=form.cleaned_data["image"].image.width,
            height=form.cleaned_data["image"].image.height,
            name=form.cleaned_data.get("description"),
            state=PostAttachmentStates.fetched,
        )
        attachment.file.save(
            form.cleaned_data["image"].name,
            form.cleaned_data["image"],
        )
        attachment.thumbnail.save(
            form.cleaned_data["image"].name,
            thumbnail_file,
        )
        attachment.save()
        # Return the response, with a hidden input plus a note
        return render(
            self.request, "activities/_image_uploaded.html", {"attachment": attachment}
        )
