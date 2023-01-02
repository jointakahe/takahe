from urllib.parse import urlparse

import httpx
import urlman
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template.loader import render_to_string

from core.ld import canonicalise, get_list
from core.models import Config
from stator.models import State, StateField, StateGraph, StatorModel
from users.models import Domain


class ReportStates(StateGraph):
    new = State(try_interval=600)
    sent = State()

    new.transitions_to(sent)

    @classmethod
    async def handle_new(cls, instance: "Report"):
        """
        Sends the report to the remote server if we need to
        """
        from users.models import SystemActor, User

        recipients = []
        report = await instance.afetch_full()
        async for mod in User.objects.filter(
            models.Q(moderator=True) | models.Q(admin=True)
        ).values_list("email", flat=True):
            recipients.append(mod)

        if report.forward and not report.subject_identity.domain.local:
            system_actor = SystemActor()
            try:
                await system_actor.signed_request(
                    method="post",
                    uri=report.subject_identity.inbox_uri,
                    body=canonicalise(report.to_ap()),
                )
            except httpx.RequestError:
                pass
        email = EmailMultiAlternatives(
            subject=f"{Config.system.site_name}: New Moderation Report",
            body=render_to_string(
                "emails/report_new.txt",
                {
                    "report": report,
                    "config": Config.system,
                    "settings": settings,
                },
            ),
            from_email=settings.SERVER_EMAIL,
            bcc=recipients,
        )
        email.attach_alternative(
            content=render_to_string(
                "emails/report_new.html",
                {
                    "report": report,
                    "config": Config.system,
                    "settings": settings,
                },
            ),
            mimetype="text/html",
        )
        await sync_to_async(email.send)()
        return cls.sent


class Report(StatorModel):
    """
    A complaint about a user or post.
    """

    class Types(models.TextChoices):
        spam = "spam"
        hateful = "hateful"
        illegal = "illegal"
        remote = "remote"
        other = "other"

    state = StateField(ReportStates)

    subject_identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="reports",
    )
    subject_post = models.ForeignKey(
        "activities.Post",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reports",
    )

    source_identity = models.ForeignKey(
        "users.Identity",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="filed_reports",
    )
    source_domain = models.ForeignKey(
        "users.Domain",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="filed_reports",
    )

    moderator = models.ForeignKey(
        "users.Identity",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="moderated_reports",
    )

    type = models.CharField(max_length=100, choices=Types.choices)
    complaint = models.TextField()
    forward = models.BooleanField(default=False)
    valid = models.BooleanField(null=True)

    seen = models.DateTimeField(blank=True, null=True)
    resolved = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class urls(urlman.Urls):
        admin = "/admin/reports/"
        admin_view = "{admin}{self.pk}/"

    ### ActivityPub ###

    async def afetch_full(self) -> "Report":
        return await Report.objects.select_related(
            "source_identity",
            "source_domain",
            "subject_identity__domain",
            "subject_identity",
            "subject_post",
        ).aget(pk=self.pk)

    @classmethod
    def handle_ap(cls, data):
        """
        Handles an incoming flag
        """
        from activities.models import Post
        from users.models import Identity

        # Fetch the system actor
        domain_id = urlparse(data["actor"]).hostname
        # Resolve the objects into items
        objects = get_list(data, "object")
        subject_identity = None
        subject_post = None
        for object in objects:
            identity = Identity.objects.filter(local=True, actor_uri=object).first()
            post = Post.objects.filter(local=True, object_uri=object).first()
            if identity:
                subject_identity = identity
            if post:
                subject_post = post
        if subject_identity is None:
            raise ValueError("Cannot handle flag: no identity object")
        # Make a report object
        cls.objects.create(
            subject_identity=subject_identity,
            subject_post=subject_post,
            source_domain=Domain.get_remote_domain(domain_id),
            type="remote",
            complaint=data.get("content"),
        )

    def to_ap(self):
        from users.models import SystemActor

        system_actor = SystemActor()
        if self.subject_post:
            objects = [
                self.subject_post.object_uri,
                self.subject_identity.actor_uri,
            ]
        else:
            objects = self.subject_identity.actor_uri
        return {
            "id": f"https://{self.source_domain.uri_domain}/reports/{self.id}/",
            "type": "Flag",
            "actor": system_actor.actor_uri,
            "object": objects,
            "content": self.complaint,
        }
