"""Корневой маршрут: распределяет пользователя по ролям."""
from flask import Blueprint, redirect, url_for
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    if current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("scan.scanner"))


@main_bp.route("/healthz")
def healthz():
    return {"status": "ok"}
