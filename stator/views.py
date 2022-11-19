from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views import View

from stator.models import StatorModel
from stator.runner import StatorRunner


class RequestRunner(View):
    """
    Runs a Stator runner within a HTTP request. For when you're on something
    serverless.
    """

    async def get(self, request):
        # Check the token, if supplied
        if settings.STATOR_TOKEN:
            if request.GET.get("token") != settings.STATOR_TOKEN:
                return HttpResponseForbidden()
        # Run on all models
        runner = StatorRunner(StatorModel.subclasses)
        handled = await runner.run()
        return HttpResponse(f"Handled {handled}")
