from django.conf import settings
from django.db import models

from users.models import PasswordReset, User


class UserService:
    """
    High-level user handling methods
    """

    @classmethod
    def admins(cls) -> models.QuerySet[User]:
        return User.objects.filter(admin=True)

    @classmethod
    def moderators(cls) -> models.QuerySet[User]:
        return User.objects.filter(models.Q(moderator=True) | models.Q(admin=True))

    @classmethod
    def create(cls, email: str) -> User:
        """
        Creates a new user
        """
        # Make the new user
        user = User.objects.create(email=email)
        # Auto-promote the user to admin if that setting is set
        if settings.AUTO_ADMIN_EMAIL and user.email == settings.AUTO_ADMIN_EMAIL:
            user.admin = True
            user.save()
        # Send them a password reset email
        PasswordReset.create_for_user(user)
        return user
