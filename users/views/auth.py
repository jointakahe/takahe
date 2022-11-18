from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import get_object_or_404, render
from django.views.generic import FormView

from users.models import PasswordReset, User


class Login(LoginView):

    template_name = "auth/login.html"


class Logout(LogoutView):
    pass


class Signup(FormView):

    template_name = "auth/signup.html"

    class form_class(forms.Form):

        email = forms.EmailField(
            help_text="We will send a link to this email to set your password and create your account",
        )

        def clean_email(self):
            email = self.cleaned_data.get("email").lower()
            if not email:
                return
            if User.objects.filter(email=email).exists():
                raise forms.ValidationError("This email already has an account")
            return email

    def form_valid(self, form):
        user = User.objects.create(email=form.cleaned_data["email"])
        PasswordReset.create_for_user(user)
        return render(
            self.request,
            "auth/signup_success.html",
            {"email": user.email},
        )


class TriggerReset(FormView):

    template_name = "auth/trigger_reset.html"

    class form_class(forms.Form):

        email = forms.EmailField(
            help_text="We will send a reset link to this email",
        )

        def clean_email(self):
            email = self.cleaned_data.get("email").lower()
            if not email:
                return
            if not User.objects.filter(email=email).exists():
                raise forms.ValidationError("This email does not have an account")
            return email

    def form_valid(self, form):
        PasswordReset.create_for_user(
            User.objects.get(email=form.cleaned_data["email"])
        )
        return render(
            self.request,
            "auth/trigger_reset_success.html",
            {"email": form.cleaned_data["email"]},
        )


class PerformReset(FormView):

    template_name = "auth/perform_reset.html"

    class form_class(forms.Form):

        password = forms.CharField(
            widget=forms.PasswordInput,
            help_text="Must be at least 8 characters, and contain both letters and numbers.",
        )

        repeat_password = forms.CharField(
            widget=forms.PasswordInput,
        )

        def clean_password(self):
            password = self.cleaned_data["password"]
            validate_password(password)
            return password

        def clean_repeat_password(self):
            if self.cleaned_data.get("password") != self.cleaned_data.get(
                "repeat_password"
            ):
                raise forms.ValidationError("Passwords do not match")
            return self.cleaned_data.get("repeat_password")

    def dispatch(self, request, token):
        self.reset = get_object_or_404(PasswordReset, token=token)
        return super().dispatch(request)

    def form_valid(self, form):
        self.reset.user.set_password(form.cleaned_data["password"])
        self.reset.user.save()
        self.reset.delete()
        return render(
            self.request,
            "auth/perform_reset_success.html",
            {"email": self.reset.user.email},
        )

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context["reset"] = self.reset
        return context
