import json
import ssl
from typing import Optional

import httpx
import pydantic
import urlman
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import models

from core.exceptions import capture_message
from stator.models import State, StateField, StateGraph, StatorModel
from users.schemas import NodeInfo


class DomainStates(StateGraph):
    outdated = State(try_interval=60 * 30, force_initial=True)
    updated = State(try_interval=60 * 60 * 24, attempt_immediately=False)
    connection_issue = State(externally_progressed=True)
    purged = State()

    outdated.transitions_to(updated)
    updated.transitions_to(outdated)

    outdated.transitions_to(connection_issue)
    outdated.transitions_to(purged)
    connection_issue.transitions_to(outdated)
    connection_issue.transitions_to(purged)

    outdated.times_out_to(connection_issue, 60 * 60 * 24)

    @classmethod
    async def handle_outdated(cls, instance: "Domain"):
        info = await instance.fetch_nodeinfo()
        if info:
            instance.nodeinfo = info.dict()
            await sync_to_async(instance.save)()
            return cls.updated

    @classmethod
    async def handle_updated(cls, instance: "Domain"):
        return cls.outdated


class Domain(StatorModel):
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

    state = StateField(DomainStates)

    # nodeinfo 2.0 detail about the remote server
    nodeinfo = models.JSONField(null=True, blank=True)

    # If we own this domain
    local = models.BooleanField()

    # If we have blocked this domain from interacting with us
    blocked = models.BooleanField(default=False)

    # Domains can be joinable by any user of the instance (as the default one
    # should)
    public = models.BooleanField(default=False)

    # If this is the default domain (shown as the default entry for new users)
    default = models.BooleanField(default=False)

    # Domains can also be linked to one or more users for their private use
    # This should be display domains ONLY
    users = models.ManyToManyField("users.User", related_name="domains", blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class urls(urlman.Urls):
        root = "/admin/domains/"
        create = "/admin/domains/create/"
        edit = "/admin/domains/{self.domain}/"
        delete = "{edit}delete/"
        root_federation = "/admin/federation/"
        edit_federation = "/admin/federation/{self.domain}/"

    @classmethod
    def get_remote_domain(cls, domain: str) -> "Domain":
        return cls.objects.get_or_create(domain=domain.lower(), local=False)[0]

    @classmethod
    def get_domain(cls, domain: str) -> Optional["Domain"]:
        try:
            return cls.objects.get(
                models.Q(domain=domain.lower())
                | models.Q(service_domain=domain.lower())
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
        ).order_by("-default", "domain")

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
        super().save(*args, **kwargs)

    async def fetch_nodeinfo(self) -> NodeInfo | None:
        """
        Fetch the /NodeInfo/2.0 for the domain
        """
        nodeinfo20_url = f"https://{self.domain}/nodeinfo/2.0"

        async with httpx.AsyncClient(
            timeout=settings.SETUP.REMOTE_TIMEOUT,
            headers={"User-Agent": settings.TAKAHE_USER_AGENT},
        ) as client:
            try:
                response = await client.get(
                    f"https://{self.domain}/.well-known/nodeinfo",
                    follow_redirects=True,
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError:
                pass
            except ssl.SSLCertVerificationError:
                return None
            else:
                try:
                    for link in response.json().get("links", []):
                        if (
                            link.get("rel")
                            == "http://nodeinfo.diaspora.software/ns/schema/2.0"
                        ):
                            nodeinfo20_url = link.get("href", nodeinfo20_url)
                            break
                except json.JSONDecodeError:
                    pass

            try:
                response = await client.get(
                    nodeinfo20_url,
                    follow_redirects=True,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
            except (httpx.HTTPError, ssl.SSLCertVerificationError) as ex:
                response = getattr(ex, "response", None)
                if (
                    response
                    and response.status_code < 500
                    and response.status_code not in [401, 403, 404, 406, 410]
                ):
                    raise ValueError(
                        f"Client error fetching nodeinfo: domain={self.domain}, code={response.status_code}",
                        response.content,
                    )
                return None

            try:
                info = NodeInfo(**response.json())
            except (json.JSONDecodeError, pydantic.ValidationError) as ex:
                capture_message(
                    f"Client error decoding nodeinfo: {str(ex)}",
                    extra={
                        "domain": self.domain,
                        "nodeinfo20_url": nodeinfo20_url,
                    },
                )
                return None
            return info

    @property
    def software(self):
        if self.nodeinfo:
            software = self.nodeinfo.get("software", {})
            name = software.get("name", "unknown")
            version = software.get("version", "unknown")
            return f"{name:.10} - {version:.10}"
        return None
