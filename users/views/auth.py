import markdown_it
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.views import LoginView, LogoutView
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from core.models import Config
from users.models import Invite, PasswordReset, User
from users.services import UserService


class Login(LoginView):
    class form_class(AuthenticationForm):
        error_messages = {
            "invalid_login": _("No account was found with that email and password."),
            "inactive": _("This account is inactive."),
        }

    template_name = "auth/login.html"


class Logout(LogoutView):
    pass


class Signup(FormView):

    template_name = "auth/signup.html"

    class form_class(forms.Form):

        email = forms.EmailField(
            help_text="We will send a link to this email to create your account.",
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Add the policies if they're defined
            policies = []
            if Config.system.policy_rules:
                policies.append("<a href='/pages/rules/'>Server Rules</a>")
            if Config.system.policy_terms:
                policies.append("<a href='/pages/terms/'>Terms of Service</a>")
            if Config.system.policy_privacy:
                policies.append("<a href='/pages/privacy/'>Privacy Policy</a>")
            if policies:
                links = ""
                for i, policy in enumerate(policies):
                    if i == 0:
                        links += policy
                    elif i == len(policies) - 1:
                        if len(policies) > 2:
                            links += ", and "
                        else:
                            links += " and "
                        links += policy
                    else:
                        links += ", "
                        links += policy
                self.fields["policy"] = forms.BooleanField(
                    label="Policies",
                    help_text=f"Have you read the {links}, and agree to them?",
                    widget=forms.Select(
                        choices=[(False, "I do not agree"), (True, "I agree")]
                    ),
                )

        def clean_email(self):
            email = self.cleaned_data.get("email").lower()
            if not email:
                return
            if User.objects.filter(email=email).exists():
                raise forms.ValidationError("This email already has an account")
            return email

    def dispatch(self, request, token=None, *args, **kwargs):
        # See if we have an invite token
        if token:
            self.invite = get_object_or_404(Invite, token=token)
            if not self.invite.valid:
                raise Http404()
        else:
            self.invite = None
        # Calculate if we're at or over the user limit
        self.at_max_users = False
        if (
            Config.system.signup_max_users
            and User.objects.count() >= Config.system.signup_max_users
        ):
            self.at_max_users = True
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Don't allow anything if there's no invite and no signup allowed
        if (not Config.system.signup_allowed or self.at_max_users) and not self.invite:
            return self.render_to_response(self.get_context_data())
        # Make the user
        user = UserService.create(email=form.cleaned_data["email"])
        # Drop invite uses down if it has them
        if self.invite and self.invite.uses is not None:
            self.invite.uses -= 1
            if self.invite.uses <= 0:
                self.invite.delete()
            else:
                self.invite.save()
        return render(
            self.request,
            "auth/signup_success.html",
            {"email": user.email},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if (not Config.system.signup_allowed or self.at_max_users) and not self.invite:
            del context["form"]
        if Config.system.signup_text:
            context["signup_text"] = mark_safe(
                markdown_it.MarkdownIt().render(Config.system.signup_text)
            )
        return context


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
