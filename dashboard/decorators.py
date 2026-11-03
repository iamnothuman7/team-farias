from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def _deny(request, message="Você não tem permissão para acessar esta área."):
    messages.error(request, message)
    return redirect("dashboard:redirect")


def staff_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/entrar/?next={request.path}")
        if not request.user.is_admin_role:
            raise PermissionDenied("Área restrita à administração.")
        return view(request, *args, **kwargs)

    return wrapper


def team_required(view):
    """Administração ou professores."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/entrar/?next={request.path}")
        if not (request.user.is_admin_role or request.user.is_professor):
            raise PermissionDenied("Área restrita à equipe.")
        return view(request, *args, **kwargs)

    return wrapper


def student_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/entrar/?next={request.path}")
        if not hasattr(request.user, "student"):
            messages.info(request, "Sua conta é da equipe. Use o painel de gestão.")
            return redirect("dashboard:redirect")
        return view(request, *args, **kwargs)

    return wrapper
