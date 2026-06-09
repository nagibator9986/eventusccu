"""Инициализация расширений Flask (без привязки к приложению)."""
import sqlite3

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


# Настройки SQLite на каждое соединение:
#  - foreign_keys=ON  — чтобы ondelete=CASCADE реально работал (нет «сирот»);
#  - journal_mode=WAL — параллельные чтения не блокируют запись (важно под gunicorn);
#  - busy_timeout     — ждать освобождения блокировки, а не падать сразу.
@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

login_manager.login_view = "auth.login"
login_manager.login_message = "Пожалуйста, войдите в систему."
login_manager.login_message_category = "warning"
