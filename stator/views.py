from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views import View

from stator.models import StatorModel
from stator.runner import StatorRunner


class RequestRunner(View):
    """
    Runs a Stator runner within a HTTP request.
    For when you're on something serverless.
    """

    def get(self, request):
        # Check the token, if supplied
        if not settings.STATOR_TOKEN:
            return HttpResponseForbidden("No token set")
        if request.GET.get("token") != settings.STATOR_TOKEN:
            return HttpResponseForbidden("Invalid token")
        # Run on all models
        runner = StatorRunner(StatorModel.subclasses, run_for=2)
        handled = runner.run()
        return HttpResponse(f"Handled {handled}")
