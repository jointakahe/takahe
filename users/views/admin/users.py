from django import forms
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import FormView, ListView

from users.decorators import admin_required
from users.models import User


@method_decorator(admin_required, name="dispatch")
class UsersRoot(ListView):

    template_name = "admin/users.html"
    paginate_by = 30

    def get(self, request, *args, **kwargs):
        self.query = request.GET.get("query")
        self.extra_context = {
            "section": "users",
            "query": self.query or "",
        }
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        users = User.objects.annotate(
            num_identities=models.Count("identities")
        ).order_by("created")
        if self.query:
            users = users.filter(email__icontains=self.query)
        return users


@method_decorator(admin_required, name="dispatch")
class UserEdit(FormView):

    template_name = "admin/user_edit.html"
    extra_context = {
        "section": "users",
    }

    class form_class(forms.Form):
        status = forms.ChoiceField(
            choices=[
                ("normal", "Normal User"),
                ("moderator", "Moderator"),
                ("admin", "Admin"),
                ("banned", "Banned"),
            ]
        )

    def dispatch(self, request, id, *args, **kwargs):
        self.user = get_object_or_404(User, id=id)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        status = "normal"
        if self.user.moderator:
            status = "moderator"
        if self.user.admin:
            status = "admin"
        if self.user.banned:
            status = "banned"
        return {
            "email": self.user.email,
            "status": status,
        }

    def form_valid(self, form):
        # Don't let them change themselves
        if self.user == self.request.user:
            return redirect(".")
        status = form.cleaned_data["status"]
        self.user.banned = status == "banned"
        self.user.moderator = status == "moderator"
        self.user.admin = status == "admin"
        self.user.save()
        return redirect(self.user.urls.admin)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editing_user"] = self.user
        context["same_user"] = self.user == self.request.user
        context["page"] = self.request.GET.get("page")
        return context
