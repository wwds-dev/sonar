"""Line icons for the navigation rail, drawn from inline SVG.

The rail collapses to icons alone on a small screen, so each destination needs
a glyph that survives without its name. These are 16px stroke drawings — the
same visual weight as the text they sit beside — tinted at paint time to match
the item's state, which is why they are SVG strings rather than pixmap files:
a pixmap ships one colour, and the rail needs three (selected, hover, rest).

Emoji are deliberately absent. They bring their own colours, ignore the
palette, and read differently on every platform; a stroke glyph is the same
mark everywhere and takes whatever colour the state says.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: One drawing per destination, keyed by the tab's docs name (lowercased) —
#: the stable identifier; plain names are the ones that get reworded.
_BODIES = {
    "terminal": '<polyline points="1 9 4 9 6 4 9 12 11 8 15 8"/>',
    "assets": '<path d="M2 4h12M2 8h12M2 12h8"/>',
    "wire": ('<rect x="2" y="3" width="12" height="10" rx="1.5"/>'
             '<path d="M5 6.5h6M5 9.5h4"/>'),
    "book": ('<rect x="2" y="5" width="12" height="8" rx="1.5"/>'
             '<path d="M6 5V3.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V5"/>'),
    "macro": ('<circle cx="8" cy="8" r="6"/>'
              '<path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/>'),
    "lab": ('<path d="M6 2h4M7 2v4l-3.5 6.2A1.5 1.5 0 0 0 4.8 14h6.4'
            'a1.5 1.5 0 0 0 1.3-1.8L9 6V2"/>'),
    "playmaker": ('<path d="M5 2.5h6v3a3 3 0 0 1-6 0v-3zM5 3.5H3v1'
                  'a2 2 0 0 0 2 2M11 3.5h2v1a2 2 0 0 1-2 2M8 8.5v3'
                  'M5.5 13.5h5"/>'),
    "learn": ('<path d="M8 3.5C6.5 2.5 4.5 2.5 2.5 3v9c2-.5 4-.5 5.5.5 '
              '1.5-1 3.5-1 5.5-.5V3c-2-.5-4-.5-5.5.5v9.5"/>'),
}

_TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
             'fill="none" stroke="{color}" stroke-width="1.5" '
             'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')

_cache: dict[tuple, QPixmap] = {}


def has(key: str) -> bool:
    return key in _BODIES


def pixmap(key: str, color: QColor, size: int = 16,
           device_ratio: float = 2.0) -> QPixmap:
    """The glyph, tinted. Cached — the rail repaints on every hover."""
    tag = (key, color.name(), size, device_ratio)
    pm = _cache.get(tag)
    if pm is not None:
        return pm
    body = _BODIES.get(key, _BODIES["assets"])
    svg = _TEMPLATE.format(color=color.name(), body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    px = int(size * device_ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(device_ratio)
    _cache[tag] = pm
    return pm
