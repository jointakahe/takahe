from django import forms
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from users.decorators import identity_required
from users.models import Report
from users.shortcuts import by_handle_or_404


@method_decorator(identity_required, name="dispatch")
class SubmitReport(FormView):
    """
    Submits a report on a user or a post
    """

    template_name = "users/report.html"

    class form_class(forms.Form):
        type = forms.ChoiceField(
            choices=[
                ("", "------"),
                ("spam", "Spam or inappropriate advertising"),
                ("hateful", "Hateful, abusive, or violent speech"),
                ("other", "Something else"),
            ],
            label="Why are you reporting this?",
        )

        complaint = forms.CharField(
            widget=forms.Textarea,
            help_text="Please describe why you think this should be removed",
        )

        forward = forms.BooleanField(
            widget=forms.Select(
                choices=[
                    (False, "Do not send to other server"),
                    (True, "Send to other server"),
                ]
            ),
            help_text="Should we also send an anonymous copy of this to their server?",
            required=False,
        )

    def dispatch(self, request, handle, post_id=None):
        self.identity = by_handle_or_404(self.request, handle, local=False)
        if post_id:
            self.post_obj = get_object_or_404(self.identity.posts, pk=post_id)
        else:
            self.post_obj = None
        return super().dispatch(request)

    def form_valid(self, form):
        # Create the report
        report = Report.objects.create(
            type=form.cleaned_data["type"],
            complaint=form.cleaned_data["complaint"],
            subject_identity=self.identity,
            subject_post=self.post_obj,
            source_identity=self.request.identity,
            source_domain=self.request.identity.domain,
            forward=form.cleaned_data.get("forward", False),
        )
        # Show a thanks page
        return render(
            self.request,
            "users/report_sent.html",
            {"report": report},
        )

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["identity"] = self.identity
        context["post"] = self.post_obj
        return context
