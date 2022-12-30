import string

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.syndication.views import Feed
from django.core import validators
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django.views.generic import FormView, ListView, TemplateView, View

from activities.models import Post, PostInteraction
from activities.services import TimelineService
from core.decorators import cache_page, cache_page_by_ap_json
from core.ld import canonicalise
from core.models import Config
from users.decorators import identity_required
from users.models import Domain, Follow, FollowStates, Identity, IdentityStates
from users.services import IdentityService
from users.shortcuts import by_handle_or_404


@method_decorator(vary_on_headers("Accept"), name="dispatch")
@method_decorator(cache_page_by_ap_json(public_only=True), name="dispatch")
class ViewIdentity(ListView):
    """
    Shows identity profile pages, and also acts as the Actor endpoint when
    approached with the right Accept header.
    """

    template_name = "identity/view.html"
    paginate_by = 25

    def get(self, request, handle):
        # Make sure we understand this handle
        self.identity = by_handle_or_404(
            self.request,
            handle,
            local=False,
            fetch=True,
        )
        if (
            not self.identity.local
            and self.identity.data_age > Config.system.identity_max_age
        ):
            self.identity.transition_perform(IdentityStates.outdated)
        # If they're coming in looking for JSON, they want the actor
        if request.ap_json:
            # Return actor info
            return self.serve_actor(self.identity)
        else:
            # Show normal page
            return super().get(request, identity=self.identity)

    def serve_actor(self, identity):
        # If this not a local actor, redirect to their canonical URI
        if not identity.local:
            return redirect(identity.actor_uri)
        return JsonResponse(
            canonicalise(identity.to_ap(), include_security=True),
            content_type="application/activity+json",
        )

    def get_queryset(self):
        return TimelineService(self.request.identity).identity_public(self.identity)

    def get_context_data(self):
        context = super().get_context_data()
        context["identity"] = self.identity
        context["follow"] = None
        context["reverse_follow"] = None
        context["interactions"] = PostInteraction.get_post_interactions(
            context["page_obj"],
            self.request.identity,
        )
        context["post_count"] = self.identity.posts.count()
        if self.identity.config_identity.visible_follows:
            context["followers_count"] = self.identity.inbound_follows.filter(
                state__in=FollowStates.group_active()
            ).count()
            context["following_count"] = self.identity.outbound_follows.filter(
                state__in=FollowStates.group_active()
            ).count()
        if self.request.identity:
            follow = Follow.maybe_get(self.request.identity, self.identity)
            if follow and follow.state in FollowStates.group_active():
                context["follow"] = follow
            reverse_follow = Follow.maybe_get(self.identity, self.request.identity)
            if reverse_follow and reverse_follow.state in FollowStates.group_active():
                context["reverse_follow"] = reverse_follow
        return context


@method_decorator(
    cache_page("cache_timeout_identity_feed", public_only=True), name="__call__"
)
class IdentityFeed(Feed):
    """
    Serves a local user's Public posts as an RSS feed
    """

    def get_object(self, request, handle):
        return by_handle_or_404(
            request,
            handle,
            local=True,
        )

    def title(self, identity: Identity):
        return identity.name

    def description(self, identity: Identity):
        return f"Public posts from @{identity.handle}"

    def link(self, identity: Identity):
        return identity.absolute_profile_uri()

    def items(self, identity: Identity):
        return TimelineService(None).identity_public(identity)[:20]

    def item_description(self, item: Post):
        return item.safe_content_remote()

    def item_link(self, item: Post):
        return item.absolute_object_uri()

    def item_pubdate(self, item: Post):
        return item.published


class IdentityFollows(ListView):
    """
    Shows following/followers for an identity.
    """

    template_name = "identity/follows.html"
    paginate_by = 25
    inbound = False

    def get(self, request, handle):
        self.identity = by_handle_or_404(
            self.request,
            handle,
            local=False,
        )
        if not Config.load_identity(self.identity).visible_follows:
            raise Http404("Hidden follows")
        return super().get(request, identity=self.identity)

    def get_queryset(self):
        if self.inbound:
            return IdentityService(self.identity).followers()
        else:
            return IdentityService(self.identity).following()

    def get_context_data(self):
        context = super().get_context_data()
        context["identity"] = self.identity
        context["inbound"] = self.inbound
        context["follows_page"] = True
        context["followers_count"] = self.identity.inbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["following_count"] = self.identity.outbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["post_count"] = self.identity.posts.count()
        return context


@method_decorator(identity_required, name="dispatch")
class ActionIdentity(View):
    def post(self, request, handle):
        identity = by_handle_or_404(self.request, handle, local=False)
        # See what action we should perform
        action = self.request.POST["action"]
        if action == "follow":
            IdentityService(identity).follow_from(self.request.identity)
        elif action == "unfollow":
            IdentityService(identity).unfollow_from(self.request.identity)
        elif action == "hide_boosts":
            IdentityService(identity).follow_from(self.request.identity, boosts=False)
        elif action == "show_boosts":
            IdentityService(identity).follow_from(self.request.identity, boosts=True)
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
        discoverable = forms.BooleanField(
            help_text="If this user is visible on the frontpage and in user directories.",
            initial=True,
            widget=forms.Select(
                choices=[(True, "Discoverable"), (False, "Not Discoverable")]
            ),
            required=False,
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
                if value in ["__system__"]:
                    raise forms.ValidationError(
                        "This username is reserved for system use."
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
                and Identity.objects.filter(
                    username__iexact=username,
                    domain=domain.lower(),
                ).exists()
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
            username=username,
            domain_id=domain,
            name=form.cleaned_data["name"],
            local=True,
            discoverable=form.cleaned_data["discoverable"],
        )
        new_identity.users.add(self.request.user)
        new_identity.generate_keypair()
        self.request.session["identity_id"] = new_identity.id
        return redirect(new_identity.urls.view)
