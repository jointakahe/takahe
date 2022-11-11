import urlman
from django.db import models


class Status(models.Model):
    class StatusVisibility(models.IntegerChoices):
        public = 0
        unlisted = 1
        followers = 2
        mentioned = 3

    identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.PROTECT,
        related_name="statuses",
    )

    local = models.BooleanField()
    uri = models.CharField(max_length=500, blank=True, null=True)
    visibility = models.IntegerField(
        choices=StatusVisibility.choices,
        default=StatusVisibility.public,
    )
    text = models.TextField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    deleted = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "statuses"

    @classmethod
    def create_local(cls, identity, text: str):
        return cls.objects.create(
            identity=identity,
            text=text,
            local=True,
        )

    class urls(urlman.Urls):
        view = "{self.identity.urls.view}statuses/{self.id}/"
