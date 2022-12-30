import json

from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from activities.models import Post
from core import exceptions
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
from users.shortcuts import by_handle_or_404


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
        local_identities = Identity.objects.filter(local=True).count()
        local_posts = Post.objects.filter(local=True).count()
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
                "metadata": {},
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
        # Find the Identity by the actor on the incoming item
        # This ensures that the signature used for the headers matches the actor
        # described in the payload.
        identity = Identity.by_actor_uri(document["actor"], create=True, transient=True)
        if (
            document["type"] == "Delete"
            and document["actor"] == document["object"]
            and not identity.pk
        ):
            # We don't have an Identity record for the user. No-op
            exceptions.capture_message(
                f"Inbox: Discarded delete message for unknown actor {document['actor']}"
            )
            return HttpResponse(status=202)

        if not identity.public_key:
            # See if we can fetch it right now
            async_to_sync(identity.fetch_actor)()

        if not identity.public_key:
            exceptions.capture_message(
                f"Inbox error: cannot fetch actor {document['actor']}"
            )
            return HttpResponseBadRequest("Cannot retrieve actor")

        # See if it's from a blocked user or domain
        if identity.blocked or identity.domain.blocked:
            # I love to lie! Throw it away!
            exceptions.capture_message(
                f"Inbox: Discarded message from {identity.actor_uri}"
            )
            return HttpResponse(status=202)

        # If there's a "signature" payload, verify against that
        if "signature" in document:
            try:
                LDSignature.verify_signature(document, identity.public_key)
            except VerificationFormatError as e:
                exceptions.capture_message(
                    f"Inbox error: Bad LD signature format: {e.args[0]}"
                )
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                exceptions.capture_message("Inbox error: Bad LD signature")
                return HttpResponseUnauthorized("Bad signature")

        # Otherwise, verify against the header (assuming it's the same actor)
        else:
            try:
                HttpSignature.verify_request(
                    request,
                    identity.public_key,
                )
            except VerificationFormatError as e:
                exceptions.capture_message(
                    f"Inbox error: Bad HTTP signature format: {e.args[0]}"
                )
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                exceptions.capture_message("Inbox error: Bad HTTP signature")
                return HttpResponseUnauthorized("Bad signature")

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
