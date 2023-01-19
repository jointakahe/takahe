import random
import string

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string

from core.models import Config
from stator.models import State, StateField, StateGraph, StatorModel


class PasswordResetStates(StateGraph):
    new = State(try_interval=300)
    sent = State()

    new.transitions_to(sent)

    @classmethod
    async def handle_new(cls, instance: "PasswordReset"):
        """
        Sends the password reset email.
        """
        reset = await instance.afetch_full()
        if reset.new_account:
            await sync_to_async(send_mail)(
                subject=f"{Config.system.site_name}: Confirm new account",
                message=render_to_string(
                    "emails/account_new.txt",
                    {
                        "reset": reset,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                html_message=render_to_string(
                    "emails/account_new.html",
                    {
                        "reset": reset,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                from_email=settings.SERVER_EMAIL,
                recipient_list=[reset.user.email],
            )
        else:
            await sync_to_async(send_mail)(
                subject=f"{Config.system.site_name}: Reset password",
                message=render_to_string(
                    "emails/password_reset.txt",
                    {
                        "reset": reset,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                html_message=render_to_string(
                    "emails/password_reset.html",
                    {
                        "reset": reset,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                from_email=settings.SERVER_EMAIL,
                recipient_list=[reset.user.email],
            )
        return cls.sent


class PasswordReset(StatorModel):
    """
    A password reset for a user (this is also how we create accounts)
    """

    state = StateField(PasswordResetStates)

    user = models.ForeignKey(
        "users.user",
        on_delete=models.CASCADE,
        related_name="password_resets",
    )

    token = models.CharField(max_length=500, unique=True)
    new_account = models.BooleanField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    @classmethod
    def create_for_user(cls, user):
        return cls.objects.create(
            user=user,
            token="".join(random.choice(string.ascii_lowercase) for i in range(42)),
            new_account=not user.password,
        )

    ### Async helpers ###

    async def afetch_full(self):
        """
        Returns a version of the object with all relations pre-loaded
        """
        return await PasswordReset.objects.select_related(
            "user",
        ).aget(pk=self.pk)
