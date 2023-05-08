import string

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.syndication.views import Feed
from django.core import validators
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.xmlutils import SimplerXMLGenerator
from django.views.decorators.vary import vary_on_headers
from django.views.generic import FormView, ListView

from activities.models import Post
from activities.services import SearchService, TimelineService
from core.decorators import cache_page, cache_page_by_ap_json
from core.ld import canonicalise
from core.models import Config
from users.models import Domain, FollowStates, Identity, IdentityStates
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
        return TimelineService(None).identity_public(self.identity)

    def get_context_data(self):
        context = super().get_context_data()
        context["identity"] = self.identity
        context["public_styling"] = True
        context["post_count"] = self.identity.posts.count()
        if self.identity.config_identity.visible_follows:
            context["followers_count"] = self.identity.inbound_follows.filter(
                state__in=FollowStates.group_active()
            ).count()
            context["following_count"] = self.identity.outbound_follows.filter(
                state__in=FollowStates.group_active()
            ).count()
        return context


class FeedWithImages(Rss201rev2Feed):
    """Extended Feed class to attach multiple images."""

    def rss_attributes(self):
        attrs = super().rss_attributes()
        attrs["xmlns:media"] = "http://search.yahoo.com/mrss/"
        attrs["xmlns:webfeeds"] = "http://webfeeds.org/rss/1.0"
        return attrs

    def add_root_elements(self, handler: SimplerXMLGenerator):
        super().add_root_elements(handler)
        handler.startElement("image", {})
        handler.addQuickElement("url", self.feed["image"]["url"])
        handler.addQuickElement("title", self.feed["image"]["title"])
        handler.addQuickElement("link", self.feed["image"]["link"])
        handler.endElement("image")
        handler.addQuickElement(
            "webfeeds:icon",
            self.feed["image"]["url"],
        )

    def add_item_elements(self, handler: SimplerXMLGenerator, item):
        super().add_item_elements(handler, item)

        for image in item["images"]:
            handler.startElement(
                "media:content",
                {
                    "url": image["url"],
                    "type": image["mime_type"],
                    "fileSize": image["length"],
                    "medium": "image",
                },
            )
            if image["description"]:
                handler.addQuickElement(
                    "media:description", image["description"], {"type": "plain"}
                )
            handler.endElement("media:content")

        for hashtag in item["hashtags"]:
            handler.addQuickElement("category", hashtag)


@method_decorator(
    cache_page("cache_timeout_identity_feed", public_only=True), name="__call__"
)
class IdentityFeed(Feed):
    """
    Serves a local user's Public posts as an RSS feed
    """

    feed_type = FeedWithImages

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

    def feed_extra_kwargs(self, identity: Identity):
        """
        Return attached images data to allow `FeedWithImages.add_item_elements()`
        to attach multiple images for each `<item>`.
        """
        image = {
            "url": identity.local_icon_url().absolute,
            "title": identity.name,
            "link": identity.absolute_profile_uri(),
        }
        return {"image": image}

    def items(self, identity: Identity):
        return TimelineService(None).identity_public(identity)[:20]

    def item_description(self, item: Post):
        return item.safe_content_remote()

    def item_link(self, item: Post):
        return item.absolute_object_uri()

    def item_pubdate(self, item: Post):
        return item.published

    def item_extra_kwargs(self, item: Post):
        """
        Return attached images data to allow `FeedWithImages.add_root_elements()`
        to add `<image>` as RSS feed icon.
        """
        images = []
        for attachment in item.attachments.all():
            images.append(
                {
                    "url": attachment.full_url().absolute,
                    "length": (str(attachment.file.size)),
                    "mime_type": (attachment.mimetype),
                    "description": (attachment.name),
                }
            )

        return {"images": images, "hashtags": item.hashtags or []}


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
        context["section"] = "follows"
        context["public_styling"] = True
        context["followers_count"] = self.identity.inbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["following_count"] = self.identity.outbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["post_count"] = self.identity.posts.count()
        return context


class IdentitySearch(FormView):
    """
    Allows an identity's posts to be searched.
    """

    template_name = "identity/search.html"

    class form_class(forms.Form):
        query = forms.CharField(help_text="The text to search for")

    def dispatch(self, request, handle):
        self.identity = by_handle_or_404(self.request, handle)
        if not Config.load_identity(self.identity).search_enabled:
            raise Http404("Search not enabled")
        return super().dispatch(request, identity=self.identity)

    def form_valid(self, form):
        self.results = SearchService(
            query=form.cleaned_data["query"], identity=self.identity
        ).search_post_content()
        return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["identity"] = self.identity
        context["section"] = "search"
        context["public_styling"] = True
        context["followers_count"] = self.identity.inbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["following_count"] = self.identity.outbound_follows.filter(
            state__in=FollowStates.group_active()
        ).count()
        context["post_count"] = self.identity.posts.count()
        context["results"] = getattr(self, "results", None)
        return context


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
        identity = IdentityService.create(
            user=self.request.user,
            username=username,
            domain=domain_instance,
            name=form.cleaned_data["name"],
            discoverable=form.cleaned_data["discoverable"],
        )
        self.request.session["identity_id"] = identity.id
        return redirect(identity.urls.view)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        if len(context["form"].fields["domain"].choices) == 0:
            context["no_valid_domains"] = True
        return context
