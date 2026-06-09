"""Сканер на входе: камера телефона + подтверждение присутствия.

Маршруты:
  GET  /scan                — страница сканера (камера).
  GET  /scan/api/lookup     — информация о госте по токену (без изменения данных).
  POST /scan/api/checkin    — отметить присутствие (идемпотентно).
"""
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import STATUS_PRESENT, Guest

scan_bp = Blueprint("scan", __name__, url_prefix="/scan")


def _extract_token(raw: str | None) -> str:
    """Достаёт токен из произвольного текста QR (URL или «голый» токен)."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        raw = raw.split("?")[0].split("#")[0]
        parts = [p for p in raw.split("/") if p]
        return parts[-1] if parts else ""
    return raw


def _fmt_local(value):
    if not value:
        return None
    offset = int(current_app.config.get("DISPLAY_TZ_OFFSET", 5))
    return (value + timedelta(hours=offset)).strftime("%d.%m.%Y %H:%M")


def _guest_payload(guest: Guest) -> dict:
    # student может быть None у «осиротевшего» гостя — деградируем мягко, без 500.
    # Телефон намеренно не отдаём (фронтенд его не использует — минимизация данных).
    student = guest.student
    return {
        "id": guest.id,
        "name": guest.full_name,
        "relation": guest.relation,
        "phrase": guest.relation_phrase,
        "student": student.full_name if student else "—",
        "group": student.group_name if student else None,
        "specialty": student.specialty if student else None,
        "status": guest.status,
        "status_label": guest.status_label,
        "present": guest.status == STATUS_PRESENT,
        "checked_in_at": _fmt_local(guest.checked_in_at),
        "checked_in_by": (
            guest.checked_in_by.full_name or guest.checked_in_by.username
            if guest.checked_in_by
            else None
        ),
        "expired": guest.is_expired,
        "expires_at": _fmt_local(guest.expires_at),
    }


@scan_bp.route("")
@login_required
def scanner():
    return render_template("scan/scanner.html")


@scan_bp.route("/api/lookup")
@login_required
def api_lookup():
    token = _extract_token(request.args.get("token"))
    if not token:
        return jsonify(ok=False, error="empty", message="Пустой код."), 400

    guest = Guest.query.filter_by(token=token).first()
    if guest is None:
        return (
            jsonify(ok=False, error="not_found", message="Приглашение не найдено."),
            404,
        )
    return jsonify(ok=True, guest=_guest_payload(guest))


@scan_bp.route("/api/checkin", methods=["POST"])
@login_required
def api_checkin():
    data = request.get_json(silent=True) or {}
    token = _extract_token(data.get("token") or request.form.get("token"))
    if not token:
        return jsonify(ok=False, error="empty", message="Пустой код."), 400

    guest = Guest.query.filter_by(token=token).first()
    if guest is None:
        return (
            jsonify(ok=False, error="not_found", message="Приглашение не найдено."),
            404,
        )

    if guest.status == STATUS_PRESENT:
        return jsonify(
            ok=True,
            already=True,
            message="Гость уже отмечен как присутствующий.",
            guest=_guest_payload(guest),
        )

    guest.mark_present(current_user)
    db.session.commit()
    return jsonify(
        ok=True,
        already=False,
        message="Присутствие подтверждено.",
        guest=_guest_payload(guest),
    )
