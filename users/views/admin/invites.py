from django import forms
from django.shortcuts import get_object_or_404, redirect
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
        email = forms.EmailField(
            required=False,
            help_text="Optional email to tie the invite to.\nYou will still need to email the user this code yourself!",
        )
        notes = forms.CharField(
            required=False,
            widget=forms.Textarea,
            help_text="Notes for other admins",
        )

    def form_valid(self, form):
        invite = Invite.create_random(email=form.cleaned_data.get("email") or None)
        return redirect(invite.urls.admin)


@method_decorator(moderator_required, name="dispatch")
class InviteView(FormView):

    template_name = "admin/invite_view.html"
    extra_context = {
        "section": "invites",
    }

    class form_class(InviteCreate.form_class):
        code = forms.CharField(disabled=True, required=False)

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
            "email": self.invite.email,
            "code": self.invite.token,
        }

    def form_valid(self, form):
        self.invite.note = form.cleaned_data.get("notes") or ""
        self.invite.email = form.cleaned_data.get("email") or None
        self.invite.save()
        return redirect(self.invite.urls.admin)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invite"] = self.invite
        return context
