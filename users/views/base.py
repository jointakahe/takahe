from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from users.shortcuts import by_handle_for_user_or_404


@method_decorator(login_required, name="dispatch")
class IdentityViewMixin:
    """
    A mixin that requires that the view has a "handle" kwarg that resolves
    to a valid identity that the current user has.
    """

    def dispatch(self, request, *args, **kwargs):
        self.identity = by_handle_for_user_or_404(request, kwargs["handle"])
        self.post_identity_setup()
        return super().dispatch(request, *args, **kwargs)

    def post_identity_setup(self):
        pass

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["identity"] = self.identity
        return context
