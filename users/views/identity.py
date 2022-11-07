import json
import string

from asgiref.sync import async_to_sync
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import parse_http_date
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView, View

from core.forms import FormHelper
from core.ld import canonicalise
from core.signatures import HttpSignature
from miniq.models import Task
from users.decorators import identity_required
from users.models import Domain, Follow, Identity
from users.shortcuts import by_handle_or_404


class ViewIdentity(TemplateView):

    template_name = "identity/view.html"

    def get_context_data(self, handle):
        identity = by_handle_or_404(
            self.request,
            handle,
            local=False,
            fetch=True,
        )
        statuses = identity.statuses.all()[:100]
        if identity.data_age > settings.IDENTITY_MAX_AGE:
            Task.submit("identity_fetch", identity.handle)
        return {
            "identity": identity,
            "statuses": statuses,
            "follow": Follow.maybe_get(self.request.identity, identity)
            if self.request.identity
            else None,
        }


@method_decorator(identity_required, name="dispatch")
class ActionIdentity(View):
    def post(self, request, handle):
        identity = by_handle_or_404(self.request, handle, local=False)
        # See what action we should perform
        action = self.request.POST["action"]
        if action == "follow":
            existing_follow = Follow.maybe_get(self.request.identity, identity)
            if not existing_follow:
                Follow.create_local(self.request.identity, identity)
        else:
            raise ValueError(f"Cannot handle identity action {action}")
        return redirect(identity.urls.view)


@method_decorator(login_required, name="dispatch")
class SelectIdentity(TemplateView):

    template_name = "identity/select.html"

    def get_context_data(self):
        return {
            "identities": Identity.objects.filter(users__pk=self.request.user.pk),
        }


@method_decorator(login_required, name="dispatch")
class ActivateIdentity(View):
    def get(self, request, handle):
        identity = by_handle_or_404(request, handle)
        if not identity.users.filter(pk=request.user.pk).exists():
            raise Http404()
        request.session["identity_id"] = identity.id
        # Get next URL, not allowing offsite links
        next = request.GET.get("next") or "/"
        if ":" in next:
            next = "/"
        return redirect("/")


@method_decorator(login_required, name="dispatch")
class CreateIdentity(FormView):

    template_name = "identity/create.html"

    class form_class(forms.Form):
        username = forms.CharField()
        name = forms.CharField()

        helper = FormHelper(submit_text="Create")

        def __init__(self, user, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["domain"] = forms.ChoiceField(
                choices=[
                    (domain.domain, domain.domain)
                    for domain in Domain.available_for_user(user)
                ]
            )

        def clean_username(self):
            # Remove any leading @
            value = self.cleaned_data["username"].lstrip("@")
            # Validate it's all ascii characters
            for character in value:
                if character not in string.ascii_letters + string.digits + "_-":
                    raise forms.ValidationError(
                        "Only the letters a-z, numbers 0-9, dashes and underscores are allowed."
                    )
            return value

        def clean(self):
            # Check for existing users
            username = self.cleaned_data["username"]
            domain = self.cleaned_data["domain"]
            if Identity.objects.filter(username=username, domain=domain).exists():
                raise forms.ValidationError(f"{username}@{domain} is already taken")

    def get_form(self):
        form_class = self.get_form_class()
        return form_class(user=self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        domain = form.cleaned_data["domain"]
        domain_instance = Domain.get_local_domain(domain)
        new_identity = Identity.objects.create(
            actor_uri=f"https://{domain_instance.uri_domain}/@{username}@{domain}/actor/",
            username=username,
            domain_id=domain,
            name=form.cleaned_data["name"],
            local=True,
        )
        new_identity.users.add(self.request.user)
        new_identity.generate_keypair()
        return redirect(new_identity.urls.view)


class Actor(View):
    """
    Returns the AP Actor object
    """

    def get(self, request, handle):
        identity = by_handle_or_404(self.request, handle)
        response = {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://w3id.org/security/v1",
            ],
            "id": identity.actor_uri,
            "type": "Person",
            "inbox": identity.actor_uri + "inbox/",
            "preferredUsername": identity.username,
            "publicKey": {
                "id": identity.key_id,
                "owner": identity.actor_uri,
                "publicKeyPem": identity.public_key,
            },
            "published": identity.created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": identity.urls.view_short.full(),
        }
        if identity.name:
            response["name"] = identity.name
        if identity.summary:
            response["summary"] = identity.summary
        return JsonResponse(canonicalise(response, include_security=True))


@method_decorator(csrf_exempt, name="dispatch")
class Inbox(View):
    """
    AP Inbox endpoint
    """

    def post(self, request, handle):
        # Verify body digest
        if "HTTP_DIGEST" in request.META:
            expected_digest = HttpSignature.calculate_digest(request.body)
            if request.META["HTTP_DIGEST"] != expected_digest:
                return HttpResponseBadRequest("Digest is incorrect")
        # Verify date header
        if "HTTP_DATE" in request.META:
            header_date = parse_http_date(request.META["HTTP_DATE"])
            if abs(timezone.now().timestamp() - header_date) > 60:
                return HttpResponseBadRequest("Date is too far away")
        # Get the signature details
        if "HTTP_SIGNATURE" not in request.META:
            return HttpResponseBadRequest("No signature present")
        signature_details = HttpSignature.parse_signature(
            request.META["HTTP_SIGNATURE"]
        )
        # Reject unknown algorithms
        if signature_details["algorithm"] != "rsa-sha256":
            return HttpResponseBadRequest("Unknown signature algorithm")
        # Create the signature payload
        headers_string = HttpSignature.headers_from_request(
            request, signature_details["headers"]
        )
        # Load the LD
        document = canonicalise(json.loads(request.body))
        # Find the Identity by the actor on the incoming item
        # This ensures that the signature used for the headers matches the actor
        # described in the payload.
        identity = Identity.by_actor_uri_with_create(document["actor"])
        if not identity.public_key:
            # See if we can fetch it right now
            async_to_sync(identity.fetch_actor)()
        if not identity.public_key:
            return HttpResponseBadRequest("Cannot retrieve actor")
        if not identity.verify_signature(
            signature_details["signature"], headers_string
        ):
            return HttpResponseBadRequest("Bad signature")
        # Hand off the item to be processed by the queue
        Task.submit("inbox_item", subject=identity.actor_uri, payload=document)
        return HttpResponse(status=202)


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
                    identity.urls.view_short.full(),
                ],
                "links": [
                    {
                        "rel": "http://webfinger.net/rel/profile-page",
                        "type": "text/html",
                        "href": identity.urls.view_short.full(),
                    },
                    {
                        "rel": "self",
                        "type": "application/activity+json",
                        "href": identity.actor_uri,
                    },
                ],
            }
        )
