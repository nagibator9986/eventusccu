"""Аутентификация: вход и выход сотрудников."""
import time
from collections import defaultdict
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)

# --- Простая защита от подбора пароля (in-memory, по IP) --------------------
# Для масштаба колледжа этого достаточно; при нескольких воркерах вынесите в Redis.
_FAILS: dict[str, list[float]] = defaultdict(list)
_MAX_FAILS = 5          # попыток
_WINDOW = 300           # за сколько секунд считаем попытки и держим блокировку


def _client_key() -> str:
    return request.remote_addr or "unknown"


def _is_locked(key: str) -> bool:
    now = time.time()
    recent = [t for t in _FAILS.get(key, []) if now - t < _WINDOW]
    _FAILS[key] = recent
    return len(recent) >= _MAX_FAILS


def _record_fail(key: str) -> None:
    _FAILS[key].append(time.time())


def _clear_fails(key: str) -> None:
    _FAILS.pop(key, None)


def _safe_next(target: str | None) -> str | None:
    """Защита от open-redirect: разрешаем только локальные пути."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    if not target.startswith("/"):
        return None
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        key = _client_key()
        if _is_locked(key):
            flash("Слишком много попыток входа. Попробуйте через несколько минут.", "error")
            return render_template("auth/login.html"), 429

        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            _record_fail(key)
            flash("Неверный логин или пароль.", "error")
        elif not user.active:
            flash("Учётная запись отключена.", "error")
        else:
            _clear_fails(key)
            login_user(user, remember=remember)
            db.session.commit()
            nxt = _safe_next(request.args.get("next"))
            return redirect(nxt or url_for("main.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("auth.login"))
