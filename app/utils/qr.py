"""Генерация QR-кода в виде data-URI (PNG, base64) для встраивания в HTML."""
import base64
import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M

# Фирменный тёмно-синий CCU для модулей QR (контраст достаточен для сканера)
QR_DARK = "#0A2E5C"
QR_LIGHT = "#FFFFFF"


def qr_data_uri(data: str, box_size: int = 10, border: int = 2) -> str:
    """Возвращает строку вида ``data:image/png;base64,...`` с QR-кодом.

    :param data: текст/URL, который кодируется в QR.
    :param box_size: размер одного модуля в пикселях.
    :param border: ширина «тихой зоны» в модулях.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=QR_DARK, back_color=QR_LIGHT)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
