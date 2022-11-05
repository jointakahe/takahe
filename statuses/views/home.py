from django import forms
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from core.forms import FormHelper
from statuses.models import Status
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class Home(FormView):

    template_name = "statuses/home.html"

    class form_class(forms.Form):
        text = forms.CharField()

        helper = FormHelper(submit_text="Post")

    def get_context_data(self):
        context = super().get_context_data()
        context.update(
            {
                "statuses": self.request.identity.statuses.all()[:100],
            }
        )
        return context

    def form_valid(self, form):
        Status.create_local(
            identity=self.request.identity,
            text=form.cleaned_data["text"],
        )
        return redirect(".")
