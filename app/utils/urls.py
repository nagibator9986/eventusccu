"""Построение публичных ссылок-приглашений.

Если в конфигурации задан ``PUBLIC_BASE_URL`` — ссылки строятся от него
(важно для рассылки родителям и для корректного QR). Иначе используется
адрес текущего запроса.
"""
from flask import current_app, url_for


def invite_url(token: str) -> str:
    """Абсолютный URL пригласительного билета по токену."""
    base = current_app.config.get("PUBLIC_BASE_URL")
    if base:
        path = url_for("invite.show", token=token)
        return base.rstrip("/") + path
    return url_for("invite.show", token=token, _external=True)
