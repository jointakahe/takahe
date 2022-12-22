import markdown_it
from django.http import JsonResponse
from django.shortcuts import redirect
from django.templatetags.static import static
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
    else:
        return About.as_view()(request)


@method_decorator(cache_page(public_only=True), name="dispatch")
class About(TemplateView):

    template_name = "about.html"

    def get_context_data(self):
        service = TimelineService(self.request.identity)
        return {
            "current_page": "about",
            "content": mark_safe(
                markdown_it.MarkdownIt().render(Config.system.site_about)
            ),
            "posts": service.local()[:10],
        }


class AppManifest(View):
    """
    Serves a PWA manifest file. This is a view as we want to drive some
    items from settings.
    """

    def get(self, request):
        return JsonResponse(
            {
                "$schema": "https://json.schemastore.org/web-manifest-combined.json",
                "name": "Takahē",
                "short_name": "Takahē",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#26323c",
                "theme_color": "#26323c",
                "description": "An ActivityPub server",
                "icons": [
                    {
                        "src": static("img/icon-128.png"),
                        "sizes": "128x128",
                        "type": "image/png",
                    },
                    {
                        "src": static("img/icon-1024.png"),
                        "sizes": "1024x1024",
                        "type": "image/png",
                    },
                ],
            }
        )


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
