from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView

from core.forms import FormHelper


class Login(LoginView):
    class form_class(AuthenticationForm):
        helper = FormHelper(submit_text="Login")

    template_name = "auth/login.html"


class Logout(LogoutView):
    pass
