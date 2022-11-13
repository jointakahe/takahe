from django.views.generic import TemplateView

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
            "identities": Identity.objects.filter(local=True),
        }
