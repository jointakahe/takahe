from functools import cached_property

import urlman
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models

from core.models import Config


class UserManager(BaseUserManager):
    """
    Custom user manager that understands emails
    """

    def create_user(self, email, password=None):
        user = self.create(email=email)
        if password:
            user.set_password(password)
            user.save()
        return user

    def create_superuser(self, email, password=None):
        user = self.create(email=email, admin=True)
        if password:
            user.set_password(password)
            user.save()
        return user


class User(AbstractBaseUser):
    """
    Custom user model that only needs an email
    """

    email = models.EmailField(unique=True)

    admin = models.BooleanField(default=False)
    moderator = models.BooleanField(default=False)
    banned = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class urls(urlman.Urls):
        admin = "/admin/users/"
        admin_edit = "{admin}{self.pk}/"

    @property
    def is_active(self):
        return not (self.deleted or self.banned)

    @property
    def is_superuser(self):
        return self.admin

    @property
    def is_staff(self):
        return self.admin

    def has_module_perms(self, module):
        return self.admin

    def has_perm(self, perm):
        return self.admin

    @cached_property
    def config_user(self) -> Config.UserOptions:
        return Config.load_user(self)
