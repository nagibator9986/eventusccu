"""Точка входа для запуска dev-сервера.

Запуск:
    python run.py                      # http://localhost:5000
    SSL_ADHOC=1 python run.py          # https (самоподписанный) — нужно для камеры на телефоне
    PORT=8080 HOST=0.0.0.0 python run.py
"""
import os

from app import create_app
from config import config_by_name

env = os.environ.get("FLASK_ENV", "default")
app = create_app(config_by_name.get(env, config_by_name["default"]))


if __name__ == "__main__":
    ssl_flag = (os.environ.get("SSL_ADHOC") or "").lower() in {"1", "true", "yes", "on"}
    ssl_context = "adhoc" if ssl_flag else None
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))

    # ВАЖНО: интерактивный отладчик Werkzeug допускает выполнение кода (RCE).
    # Никогда не включаем его при привязке к не-loopback адресу (LAN/0.0.0.0),
    # даже если DEBUG=True. На телефонах по сети это безопасно.
    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    debug = bool(app.config.get("DEBUG", False)) and is_loopback
    if app.config.get("DEBUG") and not is_loopback:
        print(f"[i] DEBUG-отладчик отключён, т.к. сервер слушает {host} (не loopback).")

    if not app.config.get("SECRET_KEY_FROM_ENV"):
        print("[!] SECRET_KEY не задан в окружении — используется временный ключ "
              "(сессии сбросятся при перезапуске). Для прод задайте SECRET_KEY в .env.")

    app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)
