import httpx
from django.conf import settings
from django.core.cache import caches
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View

from activities.models import Emoji, PostAttachment
from users.models import Identity


class BaseCacheView(View):
    """
    Base class for caching remote content.
    """

    cache_name = "media"
    item_timeout: int | None = None

    def get(self, request, **kwargs):
        self.kwargs = kwargs
        remote_url = self.get_remote_url()
        cache = caches[self.cache_name]
        cache_key = "proxy_" + remote_url
        # See if it's already cached
        cached_content = cache.get(cache_key)
        if not cached_content:
            # OK, fetch and cache it
            try:
                remote_response = httpx.get(
                    remote_url,
                    headers={"User-Agent": settings.TAKAHE_USER_AGENT},
                    follow_redirects=True,
                    timeout=settings.SETUP.REMOTE_TIMEOUT,
                )
            except httpx.RequestError:
                return HttpResponse(status=502)
            if remote_response.status_code >= 400:
                return HttpResponse(status=502)
            # We got it - shove it into the cache
            cached_content = {
                "content": remote_response.content,
                "mimetype": remote_response.headers.get(
                    "Content-Type", "application/octet-stream"
                ),
            }
            cache.set(cache_key, cached_content, timeout=self.item_timeout)
        return HttpResponse(
            cached_content["content"],
            headers={
                "Content-Type": cached_content["mimetype"],
                "Cache-Control": "public, max-age=3600",
            },
        )

    def get_remote_url(self):
        raise NotImplementedError()


class EmojiCacheView(BaseCacheView):
    """
    Caches Emoji
    """

    item_timeout = 86400 * 7  # One week

    def get_remote_url(self):
        self.emoji = get_object_or_404(Emoji, pk=self.kwargs["emoji_id"])

        if not self.emoji.remote_url:
            raise Http404()
        return self.emoji.remote_url


class IdentityIconCacheView(BaseCacheView):
    """
    Caches identity icons (avatars)
    """

    cache_name = "avatars"
    item_timeout = 86400 * 7  # One week

    def get_remote_url(self):
        self.identity = get_object_or_404(Identity, pk=self.kwargs["identity_id"])
        if self.identity.local or not self.identity.icon_uri:
            raise Http404()
        return self.identity.icon_uri


class IdentityImageCacheView(BaseCacheView):
    """
    Caches identity profile header images
    """

    item_timeout = 86400 * 7  # One week

    def get_remote_url(self):
        self.identity = get_object_or_404(Identity, pk=self.kwargs["identity_id"])
        if self.identity.local or not self.identity.image_uri:
            raise Http404()
        return self.identity.image_uri


class PostAttachmentCacheView(BaseCacheView):
    """
    Caches post media (images only, videos should always be offloaded to remote)
    """

    item_timeout = 86400 * 7  # One week

    def get_remote_url(self):
        self.post_attachment = get_object_or_404(
            PostAttachment, pk=self.kwargs["attachment_id"]
        )
        if not self.post_attachment.is_image():
            raise Http404()
        return self.post_attachment.remote_url
