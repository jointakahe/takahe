from django import forms
from django.shortcuts import redirect
from django.template.defaultfilters import linebreaks_filter
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from activities.models import Post, TimelineEvent
from core.forms import FormHelper
from users.decorators import identity_required


@method_decorator(identity_required, name="dispatch")
class Home(FormView):

    template_name = "activities/home.html"

    class form_class(forms.Form):
        text = forms.CharField()

        helper = FormHelper(submit_text="Post")

    def get_context_data(self):
        context = super().get_context_data()
        context.update(
            {
                "timeline_posts": [
                    te.subject_post
                    for te in TimelineEvent.objects.filter(
                        identity=self.request.identity,
                        type=TimelineEvent.Types.post,
                    ).order_by("-created")[:100]
                ],
            }
        )
        return context

    def form_valid(self, form):
        Post.create_local(
            author=self.request.identity,
            content=linebreaks_filter(form.cleaned_data["text"]),
        )
        return redirect(".")
