"""Публичная страница пригласительного билета (по токену)."""
from flask import Blueprint, render_template

from ..models import Guest
from ..utils import invite_url, qr_data_uri

invite_bp = Blueprint("invite", __name__)


@invite_bp.route("/i/<token>")
def show(token):
    guest = Guest.query.filter_by(token=token).first()
    if guest is None:
        return render_template("invite/invalid.html"), 404
    if guest.is_expired:
        return render_template("invite/expired.html", guest=guest), 410

    url = invite_url(token)
    qr = qr_data_uri(url, box_size=8, border=2)
    return render_template("invite/card.html", guest=guest, qr=qr)
