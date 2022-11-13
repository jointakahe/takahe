import string

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView, View

from core.config import Config
from users.decorators import identity_required
from users.models import Domain, Follow, Identity, IdentityStates
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
        posts = identity.posts.all()[:100]
        if identity.data_age > Config.load().identity_max_age:
            identity.transition_perform(IdentityStates.outdated)
        return {
            "identity": identity,
            "posts": posts,
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
        username = forms.CharField(
            help_text="Must be unique on your domain. Cannot be changed easily. Use only: a-z 0-9 _ -"
        )
        domain = forms.ChoiceField(
            help_text="Pick the domain to make this identity on. Cannot be changed later."
        )
        name = forms.CharField(
            help_text="The display name other users see. You can change this easily."
        )

        def __init__(self, user, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["domain"].choices = [
                (domain.domain, domain.domain)
                for domain in Domain.available_for_user(user)
            ]

        def clean_username(self):
            # Remove any leading @ and force it lowercase
            value = self.cleaned_data["username"].lstrip("@").lower()
            # Validate it's all ascii characters
            for character in value:
                if character not in string.ascii_letters + string.digits + "_-":
                    raise forms.ValidationError(
                        "Only the letters a-z, numbers 0-9, dashes, and underscores are allowed."
                    )
            return value

        def clean(self):
            # Check for existing users
            username = self.cleaned_data.get("username")
            domain = self.cleaned_data.get("domain")
            if (
                username
                and domain
                and Identity.objects.filter(username=username, domain=domain).exists()
            ):
                raise forms.ValidationError(f"{username}@{domain} is already taken")

    def get_form(self):
        form_class = self.get_form_class()
        return form_class(user=self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        domain = form.cleaned_data["domain"]
        domain_instance = Domain.get_domain(domain)
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
