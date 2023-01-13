from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin
from django_htmx.http import HttpResponseClientRefresh


class HTMXActionView(SingleObjectMixin, View):
    """
    Generic view that performs an action when called via HTMX and then causes
    a full page refresh.
    """

    def post(self, request, pk):
        self.action(self.get_object())
        return HttpResponseClientRefresh()

    def action(self, instance):
        raise NotImplementedError()
