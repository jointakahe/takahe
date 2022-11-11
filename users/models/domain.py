from typing import Optional

from django.db import models


class Domain(models.Model):
    """
    Represents a domain that a user can have an account on.

    For protocol reasons, if we want to allow custom usernames
    per domain, each "display" domain (the one in the handle) must either let
    us serve on it directly, or have a "service" domain that maps
    to it uniquely that we can serve on that.

    That way, someone coming in with just an Actor URI as their
    entrypoint can still try to webfinger preferredUsername@actorDomain
    and we can return an appropriate response.

    It's possible to just have one domain do both jobs, of course.
    This model also represents _other_ servers' domains, which we treat as
    display domains for now, until we start doing better probing.
    """

    domain = models.CharField(max_length=250, primary_key=True)
    service_domain = models.CharField(
        max_length=250,
        null=True,
        blank=True,
        db_index=True,
        unique=True,
    )

    # If we own this domain
    local = models.BooleanField()

    # If we have blocked this domain from interacting with us
    blocked = models.BooleanField(default=False)

    # Domains can be joinable by any user of the instance (as the default one
    # should)
    public = models.BooleanField(default=False)

    # Domains can also be linked to one or more users for their private use
    # This should be display domains ONLY
    users = models.ManyToManyField("users.User", related_name="domains", blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    @classmethod
    def get_remote_domain(cls, domain: str) -> "Domain":
        try:
            return cls.objects.get(domain=domain, local=False)
        except cls.DoesNotExist:
            return cls.objects.create(domain=domain, local=False)

    @classmethod
    def get_domain(cls, domain: str) -> Optional["Domain"]:
        try:
            return cls.objects.get(
                models.Q(domain=domain) | models.Q(service_domain=domain)
            )
        except cls.DoesNotExist:
            return None

    @property
    def uri_domain(self) -> str:
        if self.service_domain:
            return self.service_domain
        return self.domain

    @classmethod
    def available_for_user(cls, user):
        """
        Returns domains that are available for the user to put an identity on
        """
        return cls.objects.filter(
            models.Q(public=True) | models.Q(users__id=user.id),
            local=True,
        )

    def __str__(self):
        return self.domain

    def save(self, *args, **kwargs):
        # Ensure that we are not conflicting with other domains
        if Domain.objects.filter(service_domain=self.domain).exists():
            raise ValueError(
                f"Domain {self.domain} is already a service domain elsewhere!"
            )
        if self.service_domain:
            if Domain.objects.filter(domain=self.service_domain).exists():
                raise ValueError(
                    f"Service domain {self.service_domain} is already a domain elsewhere!"
                )
