"""Конфигурация приложения CCU Invite.

Все значения можно переопределить через переменные окружения (.env).
"""
import os
import secrets
from pathlib import Path

try:  # подхватываем .env, если установлен python-dotenv
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv опционален
    pass

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


class Config:
    # --- Безопасность ---------------------------------------------------
    # Если SECRET_KEY не задан в окружении — генерируем СЛУЧАЙНЫЙ ключ на запуск
    # процесса. Это исключает предсказуемый ключ «из коробки» (нельзя подделать
    # cookie/CSRF), но при перезапуске сессии сбросятся. Для прод ОБЯЗАТЕЛЬНО
    # задайте постоянный SECRET_KEY в .env.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
    SECRET_KEY_FROM_ENV = bool(os.environ.get("SECRET_KEY"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    # Защищённый cookie включаем только когда работаем по HTTPS
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    WTF_CSRF_TIME_LIMIT = None  # CSRF-токен не протухает в рамках сессии

    # --- База данных ----------------------------------------------------
    # На Railway: для SQLite укажите путь на Volume, например
    #   DATABASE_URL=sqlite:////data/ccu.db   (4 слэша = абсолютный путь)
    # для Postgres плагин Railway сам задаёт DATABASE_URL.
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url and _db_url.startswith("postgres://"):
        # SQLAlchemy 2.x требует схему postgresql://
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url or f"sqlite:///{INSTANCE_DIR / 'ccu.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Доменные настройки события ------------------------------------
    # Базовый публичный адрес для ссылок-приглашений и QR-кодов.
    # Если не задан — используется адрес из текущего запроса (request host).
    # Для рассылки родителям ОБЯЗАТЕЛЬНО укажите реальный домен, например:
    #   PUBLIC_BASE_URL=https://invite.ccu.kz
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

    # Сколько дней действует ссылка-приглашение (по ТЗ — месяц).
    INVITE_VALID_DAYS = int(os.environ.get("INVITE_VALID_DAYS", "30"))

    # Лимит гостей (родителей/родственников) на одного студента.
    MAX_GUESTS_PER_STUDENT = int(os.environ.get("MAX_GUESTS_PER_STUDENT", "3"))

    # Общая вместимость зала (0 = без ограничения). Используется в статистике.
    VENUE_CAPACITY = int(os.environ.get("VENUE_CAPACITY", "0"))

    # Смещение часового пояса для отображения дат (Казахстан = UTC+5).
    DISPLAY_TZ_OFFSET = int(os.environ.get("DISPLAY_TZ_OFFSET", "5"))

    # --- Брендинг -------------------------------------------------------
    COLLEGE_NAME = os.environ.get("COLLEGE_NAME", "Колледж Каспийского университета")
    COLLEGE_SHORT = os.environ.get("COLLEGE_SHORT", "CCU")
    COLLEGE_SITE = os.environ.get("COLLEGE_SITE", "ccu.kz")
    EVENT_TITLE = os.environ.get(
        "EVENT_TITLE", "Торжественная церемония вручения дипломов"
    )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
