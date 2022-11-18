from functools import partial

from django.db import models

from core.uploads import upload_namer
from stator.models import State, StateField, StateGraph, StatorModel


class PostAttachmentStates(StateGraph):
    new = State(try_interval=30000)
    fetched = State()

    new.transitions_to(fetched)

    @classmethod
    async def handle_new(cls, instance):
        # TODO: Fetch images to our own media storage
        pass


class PostAttachment(StatorModel):
    """
    An attachment to a Post. Could be an image, a video, etc.
    """

    post = models.ForeignKey(
        "activities.post",
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    state = StateField(graph=PostAttachmentStates)

    mimetype = models.CharField(max_length=200)

    # File may not be populated if it's remote and not cached on our side yet
    file = models.FileField(
        upload_to=partial(upload_namer, "attachments"), null=True, blank=True
    )

    remote_url = models.CharField(max_length=500, null=True, blank=True)

    # This is the description for images, at least
    name = models.TextField(null=True, blank=True)

    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    focal_x = models.IntegerField(null=True, blank=True)
    focal_y = models.IntegerField(null=True, blank=True)
    blurhash = models.TextField(null=True, blank=True)

    def is_image(self):
        return self.mimetype in [
            "image/apng",
            "image/avif",
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/webp",
        ]
