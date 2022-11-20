import string

from django import forms
from django.contrib.auth.decorators import login_required
from django.core import validators
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView, View

from core.ld import canonicalise
from core.models import Config
from users.decorators import identity_required
from users.models import Domain, Follow, FollowStates, Identity, IdentityStates
from users.shortcuts import by_handle_or_404


class ViewIdentity(TemplateView):
    """
    Shows identity profile pages, and also acts as the Actor endpoint when
    approached with the right Accept header.
    """

    template_name = "identity/view.html"

    def get(self, request, handle):
        # Make sure we understand this handle
        identity = by_handle_or_404(
            self.request,
            handle,
            local=False,
            fetch=True,
        )
        # If they're coming in looking for JSON, they want the actor
        accept = request.META.get("HTTP_ACCEPT", "text/html").lower()
        if (
            "application/json" in accept
            or "application/ld" in accept
            or "application/activity" in accept
        ):
            # Return actor info
            return self.serve_actor(identity)
        else:
            # Show normal page
            return super().get(request, identity=identity)

    def serve_actor(self, identity):
        # If this not a local actor, redirect to their canonical URI
        if not identity.local:
            return redirect(identity.actor_uri)
        return JsonResponse(canonicalise(identity.to_ap(), include_security=True))

    def get_context_data(self, identity):
        posts = identity.posts.all()[:100]
        if identity.data_age > Config.system.identity_max_age:
            identity.transition_perform(IdentityStates.outdated)
        follow = None
        reverse_follow = None
        if self.request.identity:
            follow = Follow.maybe_get(self.request.identity, identity)
            if follow and follow.state not in FollowStates.group_active():
                follow = None
            reverse_follow = Follow.maybe_get(identity, self.request.identity)
            if (
                reverse_follow
                and reverse_follow.state not in FollowStates.group_active()
            ):
                reverse_follow = None
        return {
            "identity": identity,
            "posts": posts,
            "follow": follow,
            "reverse_follow": reverse_follow,
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
            elif existing_follow.state in [
                FollowStates.undone,
                FollowStates.undone_remotely,
            ]:
                existing_follow.transition_perform(FollowStates.unrequested)
        elif action == "unfollow":
            existing_follow = Follow.maybe_get(self.request.identity, identity)
            if existing_follow:
                existing_follow.transition_perform(FollowStates.undone)
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
            self.user = user

        def clean_username(self):
            # Remove any leading @ and force it lowercase
            value = self.cleaned_data["username"].lstrip("@").lower()

            if not self.user.admin:
                # Apply username min length
                limit = int(Config.system.identity_min_length)
                validators.MinLengthValidator(limit)(value)

                # Apply username restrictions
                if value in Config.system.restricted_usernames.split():
                    raise forms.ValidationError(
                        "This username is restricted to administrators only."
                    )

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

            if not self.user.admin and (
                Identity.objects.filter(users=self.user).count()
                >= Config.system.identity_max_per_user
            ):
                raise forms.ValidationError(
                    f"You are not allowed more than {Config.system.identity_max_per_user} identities"
                )

    def get_form(self):
        form_class = self.get_form_class()
        return form_class(user=self.request.user, **self.get_form_kwargs())

    def form_valid(self, form):
        username = form.cleaned_data["username"]
        domain = form.cleaned_data["domain"]
        domain_instance = Domain.get_domain(domain)
        new_identity = Identity.objects.create(
            actor_uri=f"https://{domain_instance.uri_domain}/@{username}@{domain}/",
            username=username.lower(),
            domain_id=domain,
            name=form.cleaned_data["name"],
            local=True,
        )
        new_identity.users.add(self.request.user)
        new_identity.generate_keypair()
        return redirect(new_identity.urls.view)
