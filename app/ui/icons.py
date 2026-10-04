"""Icons drawn in code: no image files and no SVG plugin are needed."""
from __future__ import annotations

import math
import os
import tempfile

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "eth_sender_ui")


def _canvas(size: int, scale: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    return pixmap, painter


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _chevron(color: str, size: int, scale: int, down: bool) -> QPixmap:
    pixmap, painter = _canvas(size, scale)
    painter.setPen(_pen(color, 1.5))
    s = float(size)
    path = QPainterPath()
    if down:
        path.moveTo(s * 0.18, s * 0.36)
        path.lineTo(s * 0.5, s * 0.68)
        path.lineTo(s * 0.82, s * 0.36)
    else:
        path.moveTo(s * 0.36, s * 0.18)
        path.lineTo(s * 0.68, s * 0.5)
        path.lineTo(s * 0.36, s * 0.82)
    painter.drawPath(path)
    painter.end()
    return pixmap


def _dot(color: str, size: int, scale: int) -> QPixmap:
    pixmap, painter = _canvas(size, scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    painter.end()
    return pixmap


RETRY_ARROW = 100  # degrees, counterclockwise from 3 o'clock: where the arc meets the arrowhead
RETRY_GAP = 95  # degrees of the circle left open between the arc's tail and the arrowhead's base


def paint_retry(painter: QPainter, box: QRectF, color: str, width: float = 1.3) -> None:
    """A clockwise circular arrow "↻" in the style of the Copy icon: the same line width (spec 13.1).

    The arc ends at the base of a filled arrowhead instead of meeting two strokes in one point: at 14 px such strokes
    with round caps merge into a blob."""
    painter.save()
    s = box.width() / 14  # the drawing is made for 14 px
    center = box.center() + QPointF(0, 0.6 * s)  # a little lower: the arrowhead sticks out at the top
    radius = 4.5 * s
    ring = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
    painter.setPen(_pen(color, width))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # From the arrowhead counterclockwise around the left and the bottom up to the right side
    painter.drawArc(ring, RETRY_ARROW * 16, (360 - RETRY_GAP) * 16)
    angle = math.radians(RETRY_ARROW)
    base = QPointF(center.x() + radius * math.cos(angle), center.y() - radius * math.sin(angle))
    ahead = QPointF(math.sin(angle), math.cos(angle))  # the clockwise direction at the base, in screen axes
    side = QPointF(math.cos(angle), -math.sin(angle))  # across the arc, away from the center
    length, half = 3.7 * s, 2.5 * s
    head = QPainterPath()
    head.moveTo(base + side * half)
    head.lineTo(base + ahead * length)
    head.lineTo(base - side * half)
    head.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(head)
    painter.restore()


def _retry(color: str, size: int, scale: int) -> QPixmap:
    pixmap, painter = _canvas(size, scale)
    paint_retry(painter, QRectF(0, 0, size, size), color)
    painter.end()
    return pixmap


def _moon(color: str, size: int, scale: int) -> QPixmap:
    """A crescent: a circle with a smaller circle cut out at the top right."""
    pixmap, painter = _canvas(size, scale)
    s = float(size)
    disc = QPainterPath()
    disc.addEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
    cut = QPainterPath()
    cut.addEllipse(QRectF(s * 0.38, s * 0.04, s * 0.58, s * 0.58))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(disc.subtracted(cut))
    painter.end()
    return pixmap


def _sun(color: str, size: int, scale: int) -> QPixmap:
    """A sun: a disc and eight rays."""
    pixmap, painter = _canvas(size, scale)
    s = float(size)
    center = QPointF(s / 2, s / 2)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(center, s * 0.19, s * 0.19)
    painter.setPen(_pen(color, max(1.2, s * 0.09)))
    for i in range(8):
        angle = math.radians(i * 45)
        direction = QPointF(math.cos(angle), math.sin(angle))
        painter.drawLine(center + direction * (s * 0.31), center + direction * (s * 0.43))
    painter.end()
    return pixmap


def _icon(render, size: int) -> QIcon:
    """The icon at 100% and 200%. The same picture goes to the highlighted row of a list: otherwise Qt tints it with
    the highlight color, and the network dot fades (spec 13.2)."""
    icon = QIcon()
    for scale in (1, 2):
        pixmap = render(size, scale)
        pixmap.setDevicePixelRatio(scale)
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected):
            icon.addPixmap(pixmap, mode)
    return icon


def chevron_asset(name: str, color: str, size: int = 10) -> str:
    """Saves the arrow as PNG (normal and @2x) and returns the path for the style sheet."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    base = os.path.join(_CACHE_DIR, name)
    _chevron(color, size, 1, True).save(base + ".png")
    _chevron(color, size, 2, True).save(base + "@2x.png")
    return (base + ".png").replace("\\", "/")


def chevron_icon(color: str, down: bool, size: int = 10) -> QIcon:
    return _icon(lambda s, k: _chevron(color, s, k, down), size)


def dot_icon(color: str, size: int = 10) -> QIcon:
    return _icon(lambda s, k: _dot(color, s, k), size)


def retry_icon(color: str, size: int = 14) -> QIcon:
    return _icon(lambda s, k: _retry(color, s, k), size)


def moon_icon(color: str, size: int = 16) -> QIcon:
    return _icon(lambda s, k: _moon(color, s, k), size)


def sun_icon(color: str, size: int = 16) -> QIcon:
    return _icon(lambda s, k: _sun(color, s, k), size)


APP_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
# The colors in the band of the program icon: the six networks of version 1.2, the icon stays as it was
APP_ICON_NETWORKS = ("ethereum", "arbitrum", "robinhood", "optimism", "bsc", "base")


def app_icon_pixmap(size: int) -> QPixmap:
    """The program icon: a graphite square, a band of the network colors at the top and a light arrow.
    It is the same in both themes."""
    from app.networks import NETWORKS  # here, so that the icons module does not depend on networks at import

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    shape = QPainterPath()
    shape.addRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    painter.setClipPath(shape)
    painter.fillRect(QRectF(0, 0, s, s), QColor("#1C222B"))
    colors = [NETWORKS[key].color for key in APP_ICON_NETWORKS]
    band = max(2.0, round(s * 0.14))
    step = s / len(colors)
    for i, color in enumerate(colors):
        painter.fillRect(QRectF(i * step, 0, step + 1, band), QColor(color))
    pen = QPen(QColor("#EEF1F5"), max(1.5, s * 0.1))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    y = band + (s - band) * 0.5
    arrow = QPainterPath()
    arrow.moveTo(s * 0.24, y)
    arrow.lineTo(s * 0.74, y)
    arrow.moveTo(s * 0.55, y - s * 0.18)
    arrow.lineTo(s * 0.75, y)
    arrow.lineTo(s * 0.55, y + s * 0.18)
    painter.drawPath(arrow)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in APP_ICON_SIZES:
        icon.addPixmap(app_icon_pixmap(size))
    return icon
