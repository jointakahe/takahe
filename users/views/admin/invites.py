import datetime

from django import forms
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from users.decorators import moderator_required
from users.models import Invite


@method_decorator(moderator_required, name="dispatch")
class InvitesRoot(ListView):

    template_name = "admin/invites.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.extra_context = {
            "section": "invites",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return Invite.objects.order_by("created")


@method_decorator(moderator_required, name="dispatch")
class InviteCreate(FormView):

    template_name = "admin/invite_create.html"
    extra_context = {
        "section": "invites",
    }

    class form_class(forms.Form):
        uses = forms.IntegerField(
            required=False,
            help_text="Number of times this can be used. Leave blank for infinite uses.",
        )
        expires_days = forms.IntegerField(
            required=False,
            help_text="Number of days until this expires. Leave blank to make it last forever.",
        )
        notes = forms.CharField(
            required=False,
            help_text="Notes for other admins",
        )

    def form_valid(self, form):
        expires_days = form.cleaned_data.get("expires_days")
        invite = Invite.create_random(
            uses=form.cleaned_data.get("uses") or None,
            expires=(
                timezone.now() + datetime.timedelta(days=expires_days)
                if expires_days is not None
                else None
            ),
            note=form.cleaned_data.get("notes"),
        )
        return redirect(invite.urls.admin_view)


@method_decorator(moderator_required, name="dispatch")
class InviteView(FormView):

    template_name = "admin/invite_view.html"
    extra_context = {
        "section": "invites",
    }

    class form_class(InviteCreate.form_class):
        link = forms.CharField(disabled=True, required=False)

    def dispatch(self, request, id, *args, **kwargs):
        self.invite = get_object_or_404(Invite, id=id)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "delete" in request.POST:
            self.invite.delete()
            return redirect(self.invite.urls.admin)
        return super().post(request, *args, **kwargs)

    def get_initial(self):
        return {
            "notes": self.invite.note,
            "uses": self.invite.uses,
            "link": f"https://{settings.MAIN_DOMAIN}/auth/signup/{self.invite.token}/",
        }

    def form_valid(self, form):
        expires_days = form.cleaned_data.get("expires_days")
        self.invite.note = form.cleaned_data.get("notes") or ""
        self.invite.uses = form.cleaned_data.get("uses") or None
        self.invite.expires = (
            timezone.now() + datetime.timedelta(days=expires_days)
            if expires_days is not None
            else None
        )
        self.invite.save()
        return redirect(self.invite.urls.admin)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invite"] = self.invite
        context["page"] = self.request.GET.get("page")
        return context
