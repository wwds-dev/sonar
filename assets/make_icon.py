"""One-off generator for the app icon (run manually, not at app runtime).

A sonar sweep: concentric returns on a deep-blue field, with one bright contact
off-centre. The app listens to markets and reports what is actually out there.

    python assets/make_icon.py

Drawn with QPainter rather than PIL so icon generation needs nothing the app
does not already depend on. Each size is rendered natively rather than
downsampled from one master, which keeps the rings crisp at 16px.
"""

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage,
                           QLinearGradient, QPainter, QPen)

ASSETS = Path(__file__).resolve().parent
ICONSET = ASSETS / "icon.iconset"

FIELD_TOP = QColor("#12314f")
FIELD_BOTTOM = QColor("#070d16")
SWEEP = QColor("#3ea6ff")
CONTACT = QColor("#e8b84b")

SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing, True)

    # rounded-square field with a depth gradient
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, FIELD_TOP)
    grad.setColorAt(1.0, FIELD_BOTTOM)
    radius = size * 0.225
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)

    centre = QPointF(size * 0.5, size * 0.56)
    stroke = max(1.0, size * 0.032)

    # three concentric returns, fading outward
    for i, frac in enumerate((0.17, 0.29, 0.41)):
        c = QColor(SWEEP)
        c.setAlpha(230 - i * 62)
        p.setPen(QPen(c, stroke, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        r = size * frac
        p.drawEllipse(centre, r, r)

    # the sweep line, up and to the right
    c = QColor(SWEEP)
    c.setAlpha(200)
    p.setPen(QPen(c, stroke, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(centre, QPointF(centre.x() + size * 0.30, centre.y() - size * 0.30))

    # one contact — the thing worth reporting
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(CONTACT))
    dot = max(1.2, size * 0.055)
    p.drawEllipse(QPointF(centre.x() + size * 0.20, centre.y() - size * 0.20),
                  dot, dot)

    p.end()
    return image


def main() -> int:
    app = QGuiApplication(sys.argv)          # noqa: F841 — QPainter needs it
    ICONSET.mkdir(exist_ok=True)
    for name, size in SIZES.items():
        draw_icon(size).save(str(ICONSET / name))

    icns = ASSETS / "icon.icns"
    try:
        subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(icns)],
                       check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"iconutil failed ({exc}); PNGs left in {ICONSET}")
        return 1
    for png in ICONSET.glob("*.png"):
        png.unlink()
    ICONSET.rmdir()
    print(f"wrote {icns}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
