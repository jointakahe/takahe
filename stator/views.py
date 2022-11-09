from django.http import HttpResponse
from django.views import View

from stator.runner import StatorRunner
from users.models import Follow


class RequestRunner(View):
    """
    Runs a Stator runner within a HTTP request. For when you're on something
    serverless.
    """

    async def get(self, request):
        runner = StatorRunner([Follow])
        handled = await runner.run()
        return HttpResponse(f"Handled {handled}")
