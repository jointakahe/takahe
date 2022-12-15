from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from stator.models import StatorModel, Stats
from users.decorators import admin_required


@method_decorator(admin_required, name="dispatch")
class Stator(TemplateView):

    template_name = "admin/stator.html"

    def get_context_data(self):
        return {
            "model_stats": {
                model._meta.verbose_name_plural.title(): Stats.get_for_model(model)
                for model in StatorModel.subclasses
            },
            "section": "stator",
        }
