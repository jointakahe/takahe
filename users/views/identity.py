import string

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView, View

from core.forms import FormHelper
from users.models import Identity
from users.shortcuts import by_handle_or_404


class ViewIdentity(TemplateView):

    template_name = "identity/view.html"

    def get_context_data(self, handle):
        identity = by_handle_or_404(self.request, handle, local=False)
        statuses = identity.statuses.all()[:100]
        return {
            "identity": identity,
            "statuses": statuses,
        }


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
        handle = forms.CharField()
        name = forms.CharField()

        helper = FormHelper(submit_text="Create")

        def clean_handle(self):
            # Remove any leading @
            value = self.cleaned_data["handle"].lstrip("@")
            # Validate it's all ascii characters
            for character in value:
                if character not in string.ascii_letters + string.digits + "_-":
                    raise forms.ValidationError(
                        "Only the letters a-z, numbers 0-9, dashes and underscores are allowed."
                    )
            # Don't allow custom domains here quite yet
            if "@" in value:
                raise forms.ValidationError(
                    "You are not allowed an @ sign in your handle."
                )
            # Ensure there is a domain on the end
            if "@" not in value:
                value += "@" + settings.DEFAULT_DOMAIN
            # Check for existing users
            if Identity.objects.filter(handle=value).exists():
                raise forms.ValidationError("This handle is already taken")
            return value

    def form_valid(self, form):
        new_identity = Identity.objects.create(
            handle=form.cleaned_data["handle"],
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
        return JsonResponse(
            {
                "@context": [
                    "https://www.w3.org/ns/activitystreams",
                    "https://w3id.org/security/v1",
                ],
                "id": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.actor}",
                "type": "Person",
                "preferredUsername": identity.short_handle,
                "inbox": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.inbox}",
                "publicKey": {
                    "id": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.actor}#main-key",
                    "owner": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.actor}",
                    "publicKeyPem": identity.public_key,
                },
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class Inbox(View):
    """
    AP Inbox endpoint
    """

    def post(self, request, handle):
        # Validate the signature
        signature = request.META.get("HTTP_SIGNATURE")
        print(signature)
        print(request.body)


class Webfinger(View):
    """
    Services webfinger requests
    """

    def get(self, request):
        resource = request.GET.get("resource")
        if not resource.startswith("acct:"):
            raise Http404("Not an account resource")
        handle = resource[5:]
        identity = by_handle_or_404(request, handle)
        return JsonResponse(
            {
                "subject": f"acct:{identity.handle}",
                "aliases": [
                    f"https://{settings.DEFAULT_DOMAIN}/@{identity.short_handle}",
                ],
                "links": [
                    {
                        "rel": "http://webfinger.net/rel/profile-page",
                        "type": "text/html",
                        "href": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.view}",
                    },
                    {
                        "rel": "self",
                        "type": "application/activity+json",
                        "href": f"https://{settings.DEFAULT_DOMAIN}{identity.urls.actor}",
                    },
                ],
            }
        )
