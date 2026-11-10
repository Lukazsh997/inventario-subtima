from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.listing import apply_search, paginate

from . import services
from .forms import LoginForm, PasswordSetForm, UserCreateForm, UserUpdateForm
from .models import User
from .permissions import Capability, require_capability
from .roles import Role


def _apply_validation_error(form, error: ValidationError) -> None:
    for message in error.messages:
        form.add_error(None, message)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        if services.is_locked(username):
            form.add_error(
                None, "Conta bloqueada temporariamente por excesso de tentativas. Tente novamente mais tarde."
            )
        elif form.is_valid():
            user = form.get_user()
            login(request, user)
            services.register_login_success(user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}, request.is_secure()):
                return redirect(next_url)
            return redirect("core:home")
        else:
            services.register_login_failure(username)
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    services.register_logout(request.user)
    logout(request)
    return redirect("accounts:login")


@require_http_methods(["GET", "POST"])
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        services.register_password_change(user)
        messages.success(request, "Senha alterada.")
        return redirect("core:home")
    return render(request, "accounts/password_change.html", {"form": form})


# --- Gestão de usuários (Administrador) ---------------------------------------------


@require_capability(Capability.USERS_MANAGE)
def user_list(request):
    queryset = User.objects.select_related("sector")
    queryset = apply_search(queryset, request.GET.get("q"), ["username", "full_name", "email"])
    role = request.GET.get("perfil")
    if role in Role.values:
        queryset = queryset.filter(role=role)
    status = request.GET.get("status", "ativos")
    if status == "ativos":
        queryset = queryset.filter(is_active=True)
    elif status == "inativos":
        queryset = queryset.filter(is_active=False)
    page, querystring = paginate(request, queryset)
    return render(
        request,
        "accounts/user_list.html",
        {
            "page": page,
            "querystring": querystring,
            "roles": Role.choices,
            "status": status,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.USERS_MANAGE)
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            user = services.create_user(
                actor=request.user,
                username=data["username"],
                full_name=data["full_name"],
                password=data["password1"],
                role=data["role"],
                sector=data["sector"],
                email=data["email"],
            )
        except ValidationError as error:
            _apply_validation_error(form, error)
        else:
            messages.success(request, f"Usuário {user.username} cadastrado.")
            return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Novo usuário"})


@require_http_methods(["GET", "POST"])
@require_capability(Capability.USERS_MANAGE)
def user_update(request, pk: int):
    user = get_object_or_404(User, pk=pk)
    initial = {"full_name": user.full_name, "email": user.email, "role": user.role, "sector": user.sector}
    form = UserUpdateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.update_user(
                actor=request.user,
                user=user,
                full_name=data["full_name"],
                role=data["role"],
                sector=data["sector"],
                email=data["email"],
            )
        except ValidationError as error:
            _apply_validation_error(form, error)
        else:
            messages.success(request, "Usuário atualizado.")
            return redirect("accounts:user_list")
    return render(
        request, "accounts/user_form.html", {"form": form, "title": f"Editar {user.username}", "edited": user}
    )


@require_POST
@require_capability(Capability.USERS_MANAGE)
def user_toggle_active(request, pk: int):
    user = get_object_or_404(User, pk=pk)
    try:
        services.set_active(actor=request.user, user=user, active=not user.is_active)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Conta reativada." if not user.is_active else "Conta desativada.")
    return redirect("accounts:user_list")


@require_http_methods(["GET", "POST"])
@require_capability(Capability.USERS_MANAGE)
def user_reset_password(request, pk: int):
    user = get_object_or_404(User, pk=pk)
    form = PasswordSetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.reset_password(actor=request.user, user=user, new_password=form.cleaned_data["password1"])
        except ValidationError as error:
            _apply_validation_error(form, error)
        else:
            messages.success(request, f"Senha de {user.username} redefinida.")
            return redirect("accounts:user_list")
    return render(request, "accounts/user_password.html", {"form": form, "edited": user})
