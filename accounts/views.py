from django.contrib.auth import views as auth_views
from django.urls import reverse

from .forms import EmailAuthenticationForm
from core.models import SiteConfiguration


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        url = self.get_redirect_url()
        return url or reverse("dashboard:redirect")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.GET.get("next", "")
        context["site"] = SiteConfiguration.current()
        return context
