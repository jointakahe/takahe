import markdown_it
from django.http import JsonResponse
from django.templatetags.static import static
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView, View

from activities.views.timelines import Home
from core.decorators import cache_page
from core.models import Config
from users.models import Identity


def homepage(request):
    if request.user.is_authenticated:
        return Home.as_view()(request)
    else:
        return LoggedOutHomepage.as_view()(request)


@method_decorator(cache_page(public_only=True), name="dispatch")
class LoggedOutHomepage(TemplateView):

    template_name = "index.html"

    def get_context_data(self):
        return {
            "about": mark_safe(
                markdown_it.MarkdownIt().render(Config.system.site_about)
            ),
            "identities": Identity.objects.filter(
                local=True,
                discoverable=True,
            ).order_by("-created")[:20],
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

    def get_context_data(self):
        if self.config_option is None:
            raise ValueError("No config option provided")
        # Get raw content
        content = getattr(Config.system, self.config_option)
        # Render it
        html = markdown_it.MarkdownIt().render(content)
        return {
            "title": self.title,
            "content": mark_safe(html),
        }
