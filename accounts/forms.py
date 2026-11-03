from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "email", "placeholder": "voce@email.com", "class": "input"}
        ),
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Sua senha", "class": "input"}
        ),
    )
    error_messages = {
        "invalid_login": "E-mail ou senha incorretos. Confira os dados e tente novamente.",
        "inactive": "Esta conta está inativa. Fale com a equipe do Team Farias.",
    }
