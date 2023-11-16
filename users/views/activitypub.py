import json
import logging
from urllib.parse import urldefrag, urlparse

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from activities.models import Post
from activities.services import TimelineService
from core.decorators import cache_page
from core.ld import canonicalise
from core.models import Config
from core.signatures import (
    HttpSignature,
    LDSignature,
    VerificationError,
    VerificationFormatError,
)
from core.views import StaticContentView
from takahe import __version__
from users.models import Identity, InboxMessage, SystemActor
from users.models.domain import Domain
from users.shortcuts import by_handle_or_404

logger = logging.getLogger(__name__)


class HttpResponseUnauthorized(HttpResponse):
    status_code = 401


class HostMeta(View):
    """
    Returns a canned host-meta response
    """

    def get(self, request):
        return HttpResponse(
            """<?xml version="1.0" encoding="UTF-8"?>
            <XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0">
            <Link rel="lrdd" template="https://%s/.well-known/webfinger?resource={uri}"/>
            </XRD>"""
            % request.headers["host"],
            content_type="application/xrd+xml",
        )


class NodeInfo(View):
    """
    Returns the well-known nodeinfo response, pointing to the 2.0 one
    """

    def get(self, request):
        host = request.META.get("HOST", settings.MAIN_DOMAIN)
        return JsonResponse(
            {
                "links": [
                    {
                        "rel": "http://nodeinfo.diaspora.software/ns/schema/2.0",
                        "href": f"https://{host}/nodeinfo/2.0/",
                    }
                ]
            }
        )


@method_decorator(cache_page(), name="dispatch")
class NodeInfo2(View):
    """
    Returns the nodeinfo 2.0 response
    """

    def get(self, request):
        # Fetch some user stats
        if request.domain:
            domain_config = Config.load_domain(request.domain)
            local_identities = Identity.objects.filter(
                local=True, domain=request.domain
            ).count()
            local_posts = Post.objects.filter(
                local=True, author__domain=request.domain
            ).count()
            metadata = {"nodeName": domain_config.site_name}
        else:
            local_identities = Identity.objects.filter(local=True).count()
            local_posts = Post.objects.filter(local=True).count()
            metadata = {}
        return JsonResponse(
            {
                "version": "2.0",
                "software": {"name": "takahe", "version": __version__},
                "protocols": ["activitypub"],
                "services": {"outbound": [], "inbound": []},
                "usage": {
                    "users": {"total": local_identities},
                    "localPosts": local_posts,
                },
                "openRegistrations": Config.system.signup_allowed,
                "metadata": metadata,
            }
        )


@method_decorator(cache_page(), name="dispatch")
class Webfinger(View):
    """
    Services webfinger requests
    """

    def get(self, request):
        resource = request.GET.get("resource")
        if not resource:
            return HttpResponseBadRequest("No resource specified")
        if not resource.startswith("acct:"):
            return HttpResponseBadRequest("Not an account resource")
        handle = resource[5:]

        if handle.startswith("__system__@"):
            # They are trying to webfinger the system actor
            actor = SystemActor()
        else:
            actor = by_handle_or_404(request, handle)

        return JsonResponse(actor.to_webfinger(), content_type="application/jrd+json")


@method_decorator(csrf_exempt, name="dispatch")
class Inbox(View):
    """
    AP Inbox endpoint
    """

    def post(self, request, handle=None):
        # Reject bodies that are unfeasibly big
        if len(request.body) > settings.JSONLD_MAX_SIZE:
            return HttpResponseBadRequest("Payload size too large")
        # Load the LD
        document = canonicalise(json.loads(request.body), include_security=True)
        document_type = document["type"]
        document_subtype = None
        if isinstance(document.get("object"), dict):
            document_subtype = document["object"].get("type")

        # Find the Identity by the actor on the incoming item
        # This ensures that the signature used for the headers matches the actor
        # described in the payload.
        if "actor" not in document:
            logger.warning("Inbox error: unspecified actor")
            return HttpResponseBadRequest("Unspecified actor")

        identity = Identity.by_actor_uri(document["actor"], create=True, transient=True)
        if (
            document_type == "Delete"
            and document["actor"] == document["object"]
            and identity._state.adding
        ):
            # We don't have an Identity record for the user. No-op
            return HttpResponse(status=202)

        # See if it's from a blocked user or domain - without calling
        # fetch_actor, which would fetch data from potentially bad actor
        domain = identity.domain
        if not domain:
            actor_url_parts = urlparse(document["actor"])
            domain = Domain.get_remote_domain(actor_url_parts.hostname)
        if identity.blocked or domain.recursively_blocked():
            # I love to lie! Throw it away!
            logger.info(
                "Inbox: Discarded message from blocked %s %s",
                "domain" if domain.recursively_blocked() else "user",
                identity.actor_uri,
            )
            return HttpResponse(status=202)

        # See if it's a type of message we know we want to ignore right now
        # (e.g. Lemmy likes/dislikes, which we can't process anyway)
        if document_type == "Announce" and document_subtype in [
            "Like",
            "Dislike",
            "Create",
            "Undo",
            "Update",
        ]:
            return HttpResponse(status=202)

        # authenticate HTTP signature first, if one is present and the actor
        # is already known to us. An invalid signature is an error and message
        # should be discarded. NOTE: for previously unknown actors, we
        # don't have their public key yet!
        if "signature" in request:
            try:
                if identity.public_key:
                    HttpSignature.verify_request(
                        request,
                        identity.public_key,
                    )
                    logger.debug(
                        "Inbox: %s from %s has good HTTP signature",
                        document_type,
                        identity,
                    )
                else:
                    logger.info(
                        "Inbox: New actor, no key available: %s",
                        document["actor"],
                    )
            except VerificationFormatError as e:
                logger.warning("Inbox error: Bad HTTP signature format: %s", e.args[0])
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                logger.warning("Inbox error: Bad HTTP signature from %s", identity)
                return HttpResponseUnauthorized("Bad signature")

        # Mastodon advices not implementing LD Signatures, but
        # they're widely deployed today. Validate it if one exists.
        # https://docs.joinmastodon.org/spec/security/#ld
        if "signature" in document:
            try:
                # signatures are identified by the signature block
                creator = urldefrag(document["signature"]["creator"]).url
                creator_identity = Identity.by_actor_uri(
                    creator, create=True, transient=True
                )
                if not creator_identity.public_key:
                    logger.info("Inbox: New actor, no key available: %s", creator)
                    # if we can't verify it, we don't keep it
                    document.pop("signature")
                else:
                    LDSignature.verify_signature(document, creator_identity.public_key)
                    logger.debug(
                        "Inbox: %s from %s has good LD signature",
                        document["type"],
                        creator_identity,
                    )
            except VerificationFormatError as e:
                logger.warning("Inbox error: Bad LD signature format: %s", e.args[0])
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                # An invalid LD Signature might also indicate nothing but
                # a syntactical difference between implementations.
                # Strip it out if we can't verify it.
                if "signature" in document:
                    document.pop("signature")
                logger.info(
                    "Inbox: Stripping invalid LD signature from %s %s",
                    creator_identity,
                    document["id"],
                )

        if not ("signature" in request or "signature" in document):
            logger.debug(
                "Inbox: %s from %s is unauthenticated. That's OK.",
                document["type"],
                identity,
            )

        # Don't allow injection of internal messages
        if document["type"].startswith("__"):
            return HttpResponseUnauthorized("Bad type")

        # Hand off the item to be processed by the queue
        InboxMessage.objects.create(message=document)
        return HttpResponse(status=202)


class Outbox(View):
    """
    The ActivityPub outbox for an identity
    """

    def get(self, request, handle):
        self.identity = by_handle_or_404(
            self.request,
            handle,
            local=False,
            fetch=True,
        )
        # If this not a local actor, 404
        if not self.identity.local:
            raise Http404("Not a local identity")
        # Return an ordered collection with the most recent 10 public posts
        posts = list(self.identity.posts.not_hidden().public()[:10])
        return JsonResponse(
            canonicalise(
                {
                    "type": "OrderedCollection",
                    "totalItems": len(posts),
                    "orderedItems": [post.to_ap() for post in posts],
                }
            ),
            content_type="application/activity+json",
        )


class FeaturedCollection(View):
    """
    An ordered collection of all pinned posts of an identity
    """

    def get(self, request, handle):
        self.identity = by_handle_or_404(
            request,
            handle,
            local=False,
            fetch=True,
        )
        if not self.identity.local:
            raise Http404("Not a local identity")
        posts = list(TimelineService(self.identity).identity_pinned())
        return JsonResponse(
            canonicalise(
                {
                    "type": "OrderedCollection",
                    "id": self.identity.actor_uri + "collections/featured/",
                    "totalItems": len(posts),
                    "orderedItems": [post.to_ap() for post in posts],
                }
            ),
            content_type="application/activity+json",
        )


@method_decorator(cache_control(max_age=60 * 15), name="dispatch")
class EmptyOutbox(StaticContentView):
    """
    A fixed-empty outbox for the system actor
    """

    content_type: str = "application/activity+json"

    def get_static_content(self) -> str | bytes:
        return json.dumps(
            canonicalise(
                {
                    "type": "OrderedCollection",
                    "totalItems": 0,
                    "orderedItems": [],
                }
            )
        )


@method_decorator(cache_control(max_age=60 * 15), name="dispatch")
class SystemActorView(StaticContentView):
    """
    Special endpoint for the overall system actor
    """

    content_type: str = "application/activity+json"

    def get_static_content(self) -> str | bytes:
        return json.dumps(
            canonicalise(
                SystemActor().to_ap(),
                include_security=True,
            )
        )
