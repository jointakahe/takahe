from django.views.generic import ListView

from activities.models import Hashtag


class ExploreTag(ListView):

    template_name = "activities/explore_tag.html"
    extra_context = {
        "current_page": "explore",
        "allows_refresh": True,
    }
    paginate_by = 20

    def get_queryset(self):
        return (
            Hashtag.objects.public()
            .filter(
                stats__total__gt=0,
            )
            .order_by("-stats__total")
        )[:20]


class Explore(ExploreTag):
    pass
