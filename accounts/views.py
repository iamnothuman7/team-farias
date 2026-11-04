from django.contrib.auth import views as auth_views
from django.urls import reverse

from .forms import EmailAuthenticationForm
from core.models import SiteConfiguration


class LogoutView(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        from school.models import PushSubscription
        if request.user.is_authenticated:
            PushSubscription.objects.filter(pk=request.session.get("push_subscription_id"), user=request.user).delete()
        return super().post(request, *args, **kwargs)


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
