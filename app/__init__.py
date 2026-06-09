"""Фабрика приложения CCU Invite."""
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from .extensions import csrf, db, login_manager

MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # За обратным прокси (Railway/Nginx) доверяем заголовкам X-Forwarded-*,
    # чтобы request.scheme=https и host определялись верно (нужно для secure-cookie
    # и абсолютных ссылок-приглашений/QR).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    _ensure_instance_dir(app)

    # --- расширения -----------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # --- модели (импорт после init для регистрации в metadata) ----------
    from . import models  # noqa: F401

    # --- блюпринты ------------------------------------------------------
    from .auth.routes import auth_bp
    from .admin.routes import admin_bp
    from .invite.routes import invite_bp
    from .scan.routes import scan_bp
    from .main.routes import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(invite_bp)
    app.register_blueprint(scan_bp)

    _register_jinja(app)
    _register_errorhandlers(app)
    _register_cli(app)

    with app.app_context():
        db.create_all()

    return app


# --------------------------------------------------------------------------
def _ensure_instance_dir(app: Flask) -> None:
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        db_path = Path(uri.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _register_jinja(app: Flask) -> None:
    offset_hours = int(app.config.get("DISPLAY_TZ_OFFSET", 5))

    def _local(value: datetime) -> datetime:
        return value + timedelta(hours=offset_hours)

    @app.template_filter("dt")
    def _fmt_dt(value):
        if not value:
            return "—"
        return _local(value).strftime("%d.%m.%Y %H:%M")

    @app.template_filter("d")
    def _fmt_date(value):
        if not value:
            return "—"
        return _local(value).strftime("%d.%m.%Y")

    @app.template_filter("dlong")
    def _fmt_date_long(value):
        if not value:
            return "—"
        v = _local(value)
        return f"{v.day} {MONTHS_RU[v.month]} {v.year} г."

    @app.context_processor
    def _inject_globals():
        return {
            "COLLEGE_NAME": app.config["COLLEGE_NAME"],
            "COLLEGE_SHORT": app.config["COLLEGE_SHORT"],
            "COLLEGE_SITE": app.config["COLLEGE_SITE"],
            "EVENT_TITLE": app.config["EVENT_TITLE"],
            "current_year": (datetime.utcnow() + timedelta(hours=offset_hours)).year,
        }


def _register_errorhandlers(app: Flask) -> None:
    from flask_wtf.csrf import CSRFError

    def _wants_json() -> bool:
        # API сканера всегда отвечает JSON, чтобы фронтенд показал понятную ошибку
        return request.path.startswith("/scan/api/") or request.is_json

    @app.errorhandler(CSRFError)
    def _csrf(e):
        if _wants_json():
            return (
                jsonify(
                    ok=False,
                    error="csrf",
                    message="Сессия истекла. Обновите страницу и войдите снова.",
                ),
                400,
            )
        return render_template("errors/403.html"), 400

    @app.errorhandler(403)
    def _403(e):
        if _wants_json():
            return jsonify(ok=False, error="forbidden", message="Доступ запрещён."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def _404(e):
        if _wants_json():
            return jsonify(ok=False, error="not_found", message="Не найдено."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def _500(e):  # pragma: no cover
        db.session.rollback()
        if _wants_json():
            return (
                jsonify(ok=False, error="server", message="Ошибка сервера. Повторите попытку."),
                500,
            )
        return render_template("errors/500.html"), 500


def _register_cli(app: Flask) -> None:
    import click

    from .models import ROLE_ADMIN, ROLE_SCANNER, User

    @app.cli.command("create-user")
    @click.option("--username", prompt=True)
    @click.option("--full-name", default="", prompt="Полное имя")
    @click.option(
        "--role",
        type=click.Choice([ROLE_ADMIN, ROLE_SCANNER]),
        default=ROLE_SCANNER,
        prompt=True,
    )
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user(username, full_name, role, password):
        """Создать пользователя (администратора или сканера)."""
        if User.query.filter_by(username=username).first():
            click.echo(f"Пользователь {username!r} уже существует.")
            return
        user = User(username=username, full_name=full_name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Создан пользователь {username!r} с ролью {role}.")

    @app.cli.command("init-db")
    def init_db():
        """Создать таблицы базы данных."""
        db.create_all()
        click.echo("База данных инициализирована.")
