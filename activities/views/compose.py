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
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
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

        def __init__(self, request, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.request = request
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
            last_post = self.request.identity.posts.order_by("-created").first()
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
        return self.form_class(request=self.request, **self.get_form_kwargs())

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
            ] = self.request.identity.config_identity.default_post_visibility
            if self.reply_to:
                initial["reply_to"] = self.reply_to.pk
                if self.reply_to.visibility == Post.Visibilities.public:
                    initial[
                        "visibility"
                    ] = self.request.identity.config_identity.default_reply_visibility
                else:
                    initial["visibility"] = self.reply_to.visibility
                initial["content_warning"] = self.reply_to.summary
                # Build a set of mentions for the content to start as
                mentioned = {self.reply_to.author}
                mentioned.update(self.reply_to.mentions.all())
                mentioned.discard(self.request.identity)
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
        image = forms.ImageField(
            widget=forms.FileInput(
                attrs={
                    "_": f"""
                        on change
                            if me.files[0].size > {settings.SETUP.MEDIA_MAX_IMAGE_FILESIZE_MB * 1024 ** 2}
                                add [@disabled=] to #upload

                                remove <ul.errorlist/>
                                make <ul.errorlist/> called errorlist
                                make <li/> called error
                                set size_in_mb to (me.files[0].size / 1024 / 1024).toFixed(2)
                                put 'File must be {settings.SETUP.MEDIA_MAX_IMAGE_FILESIZE_MB}MB or less (actual: ' + size_in_mb + 'MB)' into error
                                put error into errorlist
                                put errorlist before me
                            else
                                remove @disabled from #upload
                                remove <ul.errorlist/>
                            end
                        end
                    """
                }
            )
        )
        description = forms.CharField(required=False)

        def clean_image(self):
            value = self.cleaned_data["image"]
            max_mb = settings.SETUP.MEDIA_MAX_IMAGE_FILESIZE_MB
            max_bytes = max_mb * 1024 * 1024
            if value.size > max_bytes:
                # Erase the file from our data to stop trying to show it again
                self.files = {}
                raise forms.ValidationError(
                    f"File must be {max_mb}MB or less (actual: {value.size / 1024 ** 2:.2f})"
                )
            return value

    def form_invalid(self, form):
        return super().form_invalid(form)

    def form_valid(self, form):
        # Make a PostAttachment
        main_file = resize_image(
            form.cleaned_data["image"],
            size=(2000, 2000),
            cover=False,
        )
        thumbnail_file = resize_image(
            form.cleaned_data["image"],
            size=(400, 225),
            cover=True,
        )
        attachment = PostAttachment.objects.create(
            blurhash=blurhash_image(thumbnail_file),
            mimetype="image/webp",
            width=main_file.image.width,
            height=main_file.image.height,
            name=form.cleaned_data.get("description"),
            state=PostAttachmentStates.fetched,
        )

        attachment.file.save(
            main_file.name,
            main_file,
        )
        attachment.thumbnail.save(
            thumbnail_file.name,
            thumbnail_file,
        )
        attachment.save()
        # Return the response, with a hidden input plus a note
        return render(
            self.request, "activities/_image_uploaded.html", {"attachment": attachment}
        )
