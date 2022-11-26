from django.http import JsonResponse
from django.templatetags.static import static
from django.views.generic import TemplateView, View

from activities.views.timelines import Home
from users.models import Identity


def homepage(request):
    if request.user.is_authenticated:
        return Home.as_view()(request)
    else:
        return LoggedOutHomepage.as_view()(request)


class LoggedOutHomepage(TemplateView):

    template_name = "index.html"

    def get_context_data(self):
        return {
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
