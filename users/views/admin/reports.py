from django import forms
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from users.decorators import moderator_required
from users.models import Identity, Report


@method_decorator(moderator_required, name="dispatch")
class ReportsRoot(ListView):

    template_name = "admin/reports.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.query = request.GET.get("query")
        self.all = request.GET.get("all")
        self.extra_context = {
            "section": "reports",
            "all": self.all,
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        reports = Report.objects.select_related(
            "subject_post", "subject_identity"
        ).order_by("created")
        if not self.all:
            reports = reports.filter(resolved__isnull=True)
        return reports


@method_decorator(moderator_required, name="dispatch")
class ReportView(FormView):

    template_name = "admin/report_view.html"
    extra_context = {
        "section": "reports",
    }

    class form_class(forms.Form):
        notes = forms.CharField(widget=forms.Textarea, required=False)

    def dispatch(self, request, id, *args, **kwargs):
        self.report = get_object_or_404(Report, id=id)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "limit" in request.POST:
            self.report.subject_identity.restriction = Identity.Restriction.limited
            self.report.subject_identity.save()
        if "block" in request.POST:
            self.report.subject_identity.restriction = Identity.Restriction.blocked
            self.report.subject_identity.save()
        if "valid" in request.POST:
            self.report.resolved = timezone.now()
            self.report.valid = True
            self.report.moderator = self.request.user.identities.all()[0]
            self.report.save()
        if "invalid" in request.POST:
            self.report.resolved = timezone.now()
            self.report.valid = False
            self.report.moderator = self.request.user.identities.all()[0]
            self.report.save()
        return super().post(request, *args, **kwargs)

    def get_initial(self):
        return {"notes": self.report.notes}

    def form_valid(self, form):
        self.report.notes = form.cleaned_data["notes"]
        self.report.save()
        return redirect(".")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["report"] = self.report
        return context
