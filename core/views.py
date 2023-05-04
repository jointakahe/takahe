from typing import ClassVar

import markdown_it
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView, View
from django.views.static import serve

from activities.services.timeline import TimelineService
from activities.views.timelines import Home
from core.decorators import cache_page
from core.models import Config


def homepage(request):
    if request.user.is_authenticated:
        return Home.as_view()(request)
    elif request.domain and request.domain.config_domain.single_user:
        return redirect(f"/@{request.domain.config_domain.single_user}/")
    else:
        return About.as_view()(request)


@method_decorator(cache_page(public_only=True), name="dispatch")
class About(TemplateView):
    template_name = "about.html"

    def get_context_data(self):
        service = TimelineService(None)
        return {
            "current_page": "about",
            "content": mark_safe(
                markdown_it.MarkdownIt().render(Config.system.site_about)
            ),
            "posts": service.local()[:10],
        }


class StaticContentView(View):
    """
    A view that returns a bit of static content.
    """

    # Content type of the static payload
    content_type: str

    # The static content that will be returned by the view
    static_content: ClassVar[str | bytes]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if getattr(StaticContentView, "static_content", None) is None:
            StaticContentView.static_content = self.get_static_content()

    def get(self, request, *args, **kwargs):
        return HttpResponse(
            StaticContentView.static_content,
            content_type=self.content_type,
        )

    def get_static_content(self) -> str | bytes:
        """
        Override to generate the view's static content.
        """
        raise NotImplementedError()


@method_decorator(cache_page(60 * 60), name="dispatch")
class RobotsTxt(TemplateView):
    """
    Serves the robots.txt for Takahē

    To specify additional user-agents to disallow, use TAKAHE_ROBOTS_TXT_DISALLOWED_USER_AGENTS
    """

    template_name = "robots.txt"
    content_type = "text/plain"

    def get_context_data(self):
        return {
            "user_agents": getattr(settings, "ROBOTS_TXT_DISALLOWED_USER_AGENTS", []),
        }


class FlatPage(TemplateView):
    """
    Serves a "flat page" from a config option,
    returning 404 if it is empty.
    """

    template_name = "flatpage.html"
    config_option = None
    title = None

    def get(self, request, *args, **kwargs):
        if self.config_option is None:
            raise ValueError("No config option provided")
        self.content = getattr(Config.system, self.config_option)
        # If the content is a plain URL, then redirect to it instead
        if (
            "\n" not in self.content
            and " " not in self.content
            and "://" in self.content
        ):
            return redirect(self.content)
        return super().get(request, *args, **kwargs)

    def get_context_data(self):
        html = markdown_it.MarkdownIt().render(self.content)
        return {
            "title": self.title,
            "content": mark_safe(html),
        }


def custom_static_serve(*args, **keywords):
    """
    Set the correct `Content-Type` header for static WebP images
    since Django cannot guess the MIME type of WebP images.
    """
    response = serve(*args, **keywords)
    if keywords["path"].endswith(".webp"):
        response.headers["Content-Type"] = "image/webp"
    return response
