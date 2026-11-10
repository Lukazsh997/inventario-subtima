from django import forms
from django.contrib.auth.forms import AuthenticationForm

from apps.organization.models import Sector

from .models import User
from .roles import Role


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Login", max_length=150, widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"})
    )
    password = forms.CharField(
        label="Senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    error_messages = {
        "invalid_login": "Login ou senha incorretos.",
        "inactive": "Esta conta está desativada.",
    }


def _sector_field():
    return forms.ModelChoiceField(
        label="Setor",
        queryset=Sector.objects.filter(active=True),
        required=False,
        empty_label="— sem setor —",
    )


class UserCreateForm(forms.Form):
    username = forms.CharField(label="Login", max_length=150)
    full_name = forms.CharField(label="Nome completo", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)
    role = forms.ChoiceField(label="Perfil", choices=Role.choices, initial=Role.TECHNICIAN)
    sector = _sector_field()
    password1 = forms.CharField(
        label="Senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirme a senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Já existe um usuário com este login.")
        return username

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", "As senhas não conferem.")
        return data


class UserUpdateForm(forms.Form):
    full_name = forms.CharField(label="Nome completo", max_length=150)
    email = forms.EmailField(label="E-mail", required=False)
    role = forms.ChoiceField(label="Perfil", choices=Role.choices)
    sector = _sector_field()


class PasswordSetForm(forms.Form):
    password1 = forms.CharField(
        label="Nova senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirme a nova senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", "As senhas não conferem.")
        return data
