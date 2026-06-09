"""Декораторы контроля доступа по ролям."""
from functools import wraps

from flask import abort, redirect, url_for
from flask_login import current_user


def admin_required(view):
    """Доступ только для администраторов."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
