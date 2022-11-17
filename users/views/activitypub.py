import json

from asgiref.sync import async_to_sync
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from core.ld import canonicalise
from core.signatures import (
    HttpSignature,
    LDSignature,
    VerificationError,
    VerificationFormatError,
)
from users.models import Identity, InboxMessage
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
            % request.META["HTTP_HOST"],
            content_type="application/xml",
        )


class Webfinger(View):
    """
    Services webfinger requests
    """

    def get(self, request):
        resource = request.GET.get("resource")
        if not resource.startswith("acct:"):
            raise Http404("Not an account resource")
        handle = resource[5:].replace("testfedi", "feditest")
        identity = by_handle_or_404(request, handle)
        return JsonResponse(
            {
                "subject": f"acct:{identity.handle}",
                "aliases": [
                    str(identity.urls.view_nice),
                ],
                "links": [
                    {
                        "rel": "http://webfinger.net/rel/profile-page",
                        "type": "text/html",
                        "href": str(identity.urls.view_nice),
                    },
                    {
                        "rel": "self",
                        "type": "application/activity+json",
                        "href": identity.actor_uri,
                    },
                ],
            }
        )


class Actor(View):
    """
    Returns the AP Actor object
    """

    def get(self, request, handle):
        identity = by_handle_or_404(self.request, handle)
        return JsonResponse(canonicalise(identity.to_ap(), include_security=True))


@method_decorator(csrf_exempt, name="dispatch")
class Inbox(View):
    """
    AP Inbox endpoint
    """

    def post(self, request, handle):
        # Load the LD
        document = canonicalise(json.loads(request.body), include_security=True)
        # Find the Identity by the actor on the incoming item
        # This ensures that the signature used for the headers matches the actor
        # described in the payload.
        identity = Identity.by_actor_uri(document["actor"], create=True)
        if not identity.public_key:
            # See if we can fetch it right now
            async_to_sync(identity.fetch_actor)()
        if not identity.public_key:
            print("Cannot get actor", document["actor"])
            return HttpResponseBadRequest("Cannot retrieve actor")
        # If there's a "signature" payload, verify against that
        if "signature" in document:
            try:
                LDSignature.verify_signature(document, identity.public_key)
            except VerificationFormatError as e:
                print("Bad LD signature format:", e.args[0])
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                print("Bad LD signature")
                return HttpResponseUnauthorized("Bad signature")
        # Otherwise, verify against the header (assuming it's the same actor)
        else:
            try:
                HttpSignature.verify_request(
                    request,
                    identity.public_key,
                )
            except VerificationFormatError as e:
                print("Bad HTTP signature format:", e.args[0])
                return HttpResponseBadRequest(e.args[0])
            except VerificationError:
                print("Bad HTTP signature")
                return HttpResponseUnauthorized("Bad signature")
        # Hand off the item to be processed by the queue
        InboxMessage.objects.create(message=document)
        return HttpResponse(status=202)
