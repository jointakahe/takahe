import random
import string

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
    def handle_new(cls, instance: "PasswordReset"):
        """
        Sends the password reset email.
        """
        if instance.new_account:
            send_mail(
                subject=f"{Config.system.site_name}: Confirm new account",
                message=render_to_string(
                    "emails/account_new.txt",
                    {
                        "reset": instance,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                html_message=render_to_string(
                    "emails/account_new.html",
                    {
                        "reset": instance,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                from_email=settings.SERVER_EMAIL,
                recipient_list=[instance.user.email],
            )
        else:
            send_mail(
                subject=f"{Config.system.site_name}: Reset password",
                message=render_to_string(
                    "emails/password_reset.txt",
                    {
                        "reset": instance,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                html_message=render_to_string(
                    "emails/password_reset.html",
                    {
                        "reset": instance,
                        "config": Config.system,
                        "settings": settings,
                    },
                ),
                from_email=settings.SERVER_EMAIL,
                recipient_list=[instance.user.email],
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
