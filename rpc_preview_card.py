from __future__ import annotations

import time
import traceback
import webbrowser
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPixmap, QPainter, QPainterPath,
    QFontMetrics, QCursor, QColor,
)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, )

from config_loader import ActivityType

_CARD    = "#111214"
_SURFACE = "#2b2d31"
_HEADER  = "#1a1b1e"
_ACCENT  = "#5865f2"
_TEXT    = "#f2f3f5"
_SUBTEXT = "#b5bac1"
_MUTED   = "#80848e"
_DIVIDER = "#3a3c41"
_BTN_BG  = "#4f545c"
_BTN_HVR = "#5d6269"


class _ImageLoader(QObject):
    loaded = pyqtSignal(QPixmap, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_finished)
        self._pending: dict[object, str] = {}

    def fetch(self, url: str):
        if not url:
            return
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)
        reply = self._nam.get(req)
        self._pending[reply] = url

    def _on_finished(self, reply):
        url = self._pending.pop(reply, "")
        if reply.error() == QNetworkReply.NoError:
            px = QPixmap()
            px.loadFromData(reply.readAll())
            if not px.isNull():
                self.loaded.emit(px, url)
        reply.deleteLater()


class _ProgressBar(QWidget):
    """Discord-style progress bar showing elapsed time, a fill bar, and total duration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._progress = 0.0
        self._elapsed_text = "0:00"
        self._total_text = "0:00"
        self._is_stream = False
        self._is_paused = False

        self._bg_color   = QColor("#4f545c")
        self._fill_color = QColor("#b9bbbe")
        self._text_color = QColor("#b5bac1")

    def set_progress(self, elapsed_secs: int, total_secs: int,
                     is_stream: bool = False, is_paused: bool = False):
        self._is_stream = is_stream
        self._is_paused = is_paused

        if is_stream:
            self._elapsed_text = "LIVE"
            self._total_text = ""
            self._progress = 1.0
        else:
            self._elapsed_text = self._format_time(elapsed_secs)
            self._total_text = self._format_time(total_secs)
            self._progress = elapsed_secs / total_secs if total_secs > 0 else 0

        self.update()

    def _format_time(self, secs: int) -> str:
        h, r = divmod(abs(secs), 3600)
        m, s = divmod(r, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        fm = QFontMetrics(font)
        elapsed_width = fm.horizontalAdvance(self._elapsed_text)
        total_width = fm.horizontalAdvance(self._total_text) if self._total_text else 0

        spacing = 8

        bar_x = elapsed_width + spacing
        bar_width = self.width() - elapsed_width - total_width - (spacing * 2)
        bar_y = (self.height() - 4) // 2

        painter.setPen(self._text_color)
        painter.drawText(0, 0, elapsed_width, self.height(),
                        Qt.AlignVCenter | Qt.AlignLeft, self._elapsed_text)

        if self._is_stream:
            painter.setBrush(QColor("#f23f43"))
            painter.setPen(Qt.NoPen)
            dot_x = bar_x + bar_width // 2
            dot_y = self.height() // 2
            painter.drawEllipse(dot_x - 4, dot_y - 4, 8, 8)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._bg_color)
            painter.drawRoundedRect(bar_x, bar_y, bar_width, 4, 2, 2)

            if self._progress > 0:
                fill_width = int(bar_width * self._progress)
                painter.setBrush(self._fill_color)
                painter.drawRoundedRect(bar_x, bar_y, fill_width, 4, 2, 2)

            if self._is_paused:
                painter.setPen(QColor("#ffffff"))
                center_x = bar_x + bar_width // 2
                painter.drawRect(center_x - 2, bar_y - 2, 2, 8)
                painter.drawRect(center_x + 1, bar_y - 2, 2, 8)

        if self._total_text:
            painter.setPen(self._text_color)
            painter.drawText(self.width() - total_width, 0, total_width, self.height(),
                           Qt.AlignVCenter | Qt.AlignRight, self._total_text)

        painter.end()


def _rounded_pixmap(px: QPixmap, radius: int) -> QPixmap:
    size = px.size()
    out = QPixmap(size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size.width(), size.height(), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, px)
    p.end()
    return out


def _circle_pixmap(px: QPixmap, size: int) -> QPixmap:
    """Crop a pixmap into a perfect circle."""
    scaled = px.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (scaled.width()  - size) // 2
    y = (scaled.height() - size) // 2
    cropped = scaled.copy(x, y, size, size)
    return _rounded_pixmap(cropped, size // 2)


def _crop_center(px: QPixmap, w: int, h: int) -> QPixmap:
    x = (px.width()  - w) // 2
    y = (px.height() - h) // 2
    return px.copy(max(x, 0), max(y, 0), w, h)


class _ElideLabel(QLabel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.PlainText)

    def setText(self, text: str):
        self._full_text = text
        self.setToolTip(text if text else "")
        super().setText(text)
        self._do_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._do_elide()

    def _do_elide(self):
        if not self._full_text:
            return
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full_text, Qt.ElideRight, self.width())
        super().setText(elided)


class _DiscordButton(QFrame):
    """Clickable frame that opens a URL — mimics Discord presence buttons."""

    def __init__(self, label: str, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self.setObjectName("btn_frame")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(url)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lbl = QLabel(label)
        lbl.setObjectName("lbl_btn")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setTextFormat(Qt.PlainText)

        fm = QFontMetrics(lbl.font())
        elided = fm.elidedText(label, Qt.ElideRight, 200)
        lbl.setText(elided)
        lbl.setToolTip(label)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.addWidget(lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._url:
            webbrowser.open(self._url)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setStyleSheet(f"QFrame#btn_frame {{ background: {_BTN_HVR}; border-radius: 4px; }}")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("")
        super().leaveEvent(event)


_CARD_CSS = f"""
QFrame#rpc_card {{
    background: {_CARD};
    border-radius: 8px;
    border: 1px solid {_DIVIDER};
}}

QFrame#card_header {{
    background: {_HEADER};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid {_DIVIDER};
}}

QLabel#lbl_section {{
    color: {_TEXT};
    font-weight: 700;
    font-size: 8pt;
    letter-spacing: 0.6px;
}}

QLabel#lbl_app_name {{
    color: {_TEXT};
    font-weight: 700;
    font-size: 10pt;
}}

QLabel#lbl_username {{
    color: {_SUBTEXT};
    font-size: 8pt;
}}

QLabel#lbl_details {{
    color: {_TEXT};
    font-size: 9pt;
    font-weight: 600;
}}
QLabel#lbl_state {{
    color: {_SUBTEXT};
    font-size: 9pt;
}}

QLabel#lbl_idle {{
    color: {_MUTED};
    font-size: 9pt;
    font-style: italic;
}}

QFrame#divider {{
    background: {_DIVIDER};
    min-height: 1px;
    max-height: 1px;
}}

QFrame#btn_frame {{
    background: {_BTN_BG};
    border-radius: 4px;
}}
QLabel#lbl_btn {{
    color: {_TEXT};
    font-size: 8pt;
    font-weight: 700;
}}
"""

_AVATAR_SIZE = 40
_THUMB_SIZE  = 84
_SMALL_SIZE  = 26


class RpcPreviewCard(QWidget):
    """Discord Rich Presence preview card. Expands horizontally; text is single-line with tooltip."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._loader = _ImageLoader(self)
        self._loader.loaded.connect(self._on_image_loaded)
        self._px_cache: dict[str, QPixmap] = {}

        self._cur_large = ""
        self._cur_small = ""
        self._cur_avatar = ""

        self._end_ts:   Optional[int] = None
        self._start_ts: Optional[int] = None
        self._total_duration: int = 0
        self._position_offset: Optional[int] = None
        self._is_stream = False
        self._is_paused = False

        self._btn_widgets: list[_DiscordButton] = []

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet(_CARD_CSS)
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_timer)
        self._timer.start(1000)

        self._show_idle()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("rpc_card")
        self._card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        card_vbox = QVBoxLayout(self._card)
        card_vbox.setContentsMargins(0, 0, 0, 0)
        card_vbox.setSpacing(0)

        self._header = QFrame()
        self._header.setObjectName("card_header")
        self._header.setFixedHeight(52)

        header_lay = QHBoxLayout(self._header)
        header_lay.setContentsMargins(10, 6, 10, 6)
        header_lay.setSpacing(8)

        avatar_container = QWidget()
        avatar_container.setFixedSize(_AVATAR_SIZE + 6, _AVATAR_SIZE + 6)
        avatar_container.setStyleSheet("background:transparent;")

        self._lbl_avatar = QLabel(avatar_container)
        self._lbl_avatar.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self._lbl_avatar.setAlignment(Qt.AlignCenter)
        self._lbl_avatar.move(0, 0)
        self._lbl_avatar.setStyleSheet(
            f"background:{_SURFACE}; border-radius:{_AVATAR_SIZE//2}px;"
            f"color:{_MUTED}; font-size:16pt;"
        )
        self._lbl_avatar.setText("👤")

        self._lbl_badge = QLabel(avatar_container)
        self._lbl_badge.setFixedSize(12, 12)
        self._lbl_badge.move(_AVATAR_SIZE - 10, _AVATAR_SIZE - 10)
        self._lbl_badge.setStyleSheet(
            "background:#23a55a; border-radius:6px;"
            f"border: 2px solid {_HEADER};"
        )

        header_lay.addWidget(avatar_container)

        user_col = QVBoxLayout()
        user_col.setSpacing(1)

        self._lbl_display_name = _ElideLabel()
        self._lbl_display_name.setObjectName("lbl_app_name")

        self._lbl_username = _ElideLabel()
        self._lbl_username.setObjectName("lbl_username")

        user_col.addStretch()
        user_col.addWidget(self._lbl_display_name)
        user_col.addWidget(self._lbl_username)
        user_col.addStretch()

        header_lay.addLayout(user_col, 1)
        card_vbox.addWidget(self._header)

        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(12, 10, 12, 12)
        body_lay.setSpacing(6)

        self._lbl_section = QLabel("SEM PRESENCE ATIVA")
        self._lbl_section.setObjectName("lbl_section")
        body_lay.addWidget(self._lbl_section)

        thumb_row = QHBoxLayout()
        thumb_row.setSpacing(10)

        tc = QWidget()
        tc.setFixedSize(_THUMB_SIZE + 8, _THUMB_SIZE + 8)
        tc.setStyleSheet("background:transparent;")

        self._lbl_large = QLabel(tc)
        self._lbl_large.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._lbl_large.setAlignment(Qt.AlignCenter)
        self._lbl_large.move(0, 4)
        self._lbl_large.setStyleSheet(
            f"background:{_SURFACE}; border-radius:8px;"
            f"color:{_MUTED}; font-size:28pt;"
        )
        self._lbl_large.setText("🎵")

        self._lbl_small = QLabel(tc)
        self._lbl_small.setFixedSize(_SMALL_SIZE, _SMALL_SIZE)
        self._lbl_small.setAlignment(Qt.AlignCenter)
        self._lbl_small.move(_THUMB_SIZE - _SMALL_SIZE + 6, _THUMB_SIZE - _SMALL_SIZE + 6)
        self._lbl_small.setStyleSheet(
            f"background:{_SURFACE}; border-radius:{_SMALL_SIZE//2}px;"
            f"border: 2px solid {_CARD};"
        )
        self._lbl_small.hide()

        thumb_row.addWidget(tc)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        self._lbl_app = _ElideLabel()
        self._lbl_app.setObjectName("lbl_app_name")

        self._lbl_details = _ElideLabel()
        self._lbl_details.setObjectName("lbl_details")

        self._lbl_state = _ElideLabel()
        self._lbl_state.setObjectName("lbl_state")

        self._progress_bar = _ProgressBar()

        info_col.addStretch()
        info_col.addWidget(self._lbl_app)
        info_col.addWidget(self._lbl_details)
        info_col.addWidget(self._lbl_state)
        info_col.addWidget(self._progress_bar)
        info_col.addStretch()

        thumb_row.addLayout(info_col, 1)
        body_lay.addLayout(thumb_row)

        self._divider = QFrame()
        self._divider.setObjectName("divider")
        self._divider.hide()
        body_lay.addWidget(self._divider)

        self._btn_area = QVBoxLayout()
        self._btn_area.setSpacing(4)
        body_lay.addLayout(self._btn_area)

        self._lbl_idle = QLabel("Sem presence ativa")
        self._lbl_idle.setObjectName("lbl_idle")
        self._lbl_idle.setAlignment(Qt.AlignCenter)
        body_lay.addWidget(self._lbl_idle)

        body_lay.addStretch()
        card_vbox.addWidget(self._body)
        root.addWidget(self._card)

    def set_user(self, user_id: str, avatar_hash: str,
                 display_name: str = "", username: str = ""):
        """Update the Discord user profile shown at the top of the card."""
        self._lbl_display_name.setText(display_name or username or "User")
        self._lbl_username.setText(f"@{username}" if username else "")

        if user_id and avatar_hash:
            ext = "gif" if avatar_hash.startswith("a_") else "webp"
            url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"
            self._cur_avatar = url
            self._load_image(url, "avatar")
        else:
            self._lbl_avatar.setPixmap(QPixmap())
            self._lbl_avatar.setText("👤")

    def update_presence(self, payload: dict, track: Optional[dict] = None,
                        app_name: str = "Discord RPC (Music Bot)"):
        """Update the card with the latest presence payload."""
        try:
            self._lbl_idle.hide()
            self._divider.hide()
            self._progress_bar.show()

            act = payload.get("type", ActivityType.listening.value)
            self._lbl_section.setText({
                ActivityType.playing.value:   "JOGANDO",
                ActivityType.listening.value: "OUVINDO",
                ActivityType.watching.value:  "ASSISTINDO",
                ActivityType.competing.value: "COMPETINDO EM",
            }.get(act, "JOGANDO") + " " + app_name.upper().rsplit("#", 1)[0])

            self._lbl_app.setText(app_name)
            self._lbl_app.setHidden(True)
            details = payload.get("details", "")
            state   = payload.get("state", "").strip()
            self._lbl_details.setText(details)
            self._lbl_details.setVisible(bool(details))
            self._lbl_state.setText(state)
            self._lbl_state.setVisible(bool(state) and state != "   ")

            ts = payload.get("timestamps", {})
            self._end_ts    = ts.get("end")
            self._start_ts  = ts.get("start")
            self._is_stream = bool(track and track.get("stream"))
            self._is_paused = bool(track and track.get("paused"))

            if track and track.get("duration"):
                self._total_duration = track["duration"] // 1000
            elif self._end_ts and self._start_ts:
                self._total_duration = self._end_ts - self._start_ts
            else:
                self._total_duration = 0

            # end_ts is computed by the client as now + (duration - position), making it
            # the most accurate elapsed source; it stays in sync on every update.
            # position is only used as a static fallback when the track is paused.
            if self._is_paused and track and track.get("position") is not None:
                self._position_offset = track["position"] // 1000
            else:
                self._position_offset = None
            self._update_progress_bar()

            assets = payload.get("assets", {})
            large_url = assets.get("large_image", "")
            small_url = assets.get("small_image", "")
            self._lbl_large.setToolTip(assets.get("large_text", ""))
            self._lbl_small.setToolTip(assets.get("small_text", ""))
            self._load_image(large_url, "large")
            self._load_image(small_url, "small")

            self._rebuild_buttons(payload.get("buttons", []))
        except:
            traceback.print_exc()

    def clear_presence(self):
        self._show_idle()

    def _show_idle(self):
        self._lbl_section.setText("SEM PRESENCE ATIVA")
        self._lbl_app.setText("")
        self._lbl_details.hide()
        self._lbl_state.hide()
        self._progress_bar.hide()
        self._lbl_large.setPixmap(QPixmap())
        self._lbl_large.setText("🎵")
        self._lbl_large.setStyleSheet(
            f"background:{_SURFACE}; border-radius:8px;"
            f"color:{_MUTED}; font-size:28pt;"
        )
        self._lbl_small.hide()
        self._divider.hide()
        self._lbl_idle.show()
        self._rebuild_buttons([])
        self._end_ts = self._start_ts = None
        self._total_duration = 0
        self._position_offset = None
        self._is_stream = self._is_paused = False

    def _tick_timer(self):
        self._update_progress_bar()

    def _update_progress_bar(self):
        if self._is_stream:
            self._progress_bar.set_progress(0, 0, is_stream=True)
            return

        total = self._total_duration

        if not total:
            self._progress_bar.set_progress(0, 0)
            return

        if self._is_paused:
            elapsed = self._position_offset or 0
        elif self._end_ts:
            remaining = self._end_ts - int(time.time())
            elapsed = max(0, total - remaining)
        else:
            self._progress_bar.set_progress(0, total)
            return

        elapsed = max(0, min(elapsed, total))

        if elapsed >= total:
            self._progress_bar.set_progress(total, total, is_paused=True)
            return

        self._progress_bar.set_progress(elapsed, total, is_paused=self._is_paused)

    def _rebuild_buttons(self, buttons: list):
        for w in self._btn_widgets:
            w.setParent(None)
            w.deleteLater()
        self._btn_widgets.clear()

        if not buttons:
            self._divider.hide()
            return

        self._divider.show()
        for btn in buttons[:2]:
            label = btn.get("label", "")
            url   = btn.get("url", "")
            if not label:
                continue
            w = _DiscordButton(label, url)
            self._btn_area.addWidget(w)
            self._btn_widgets.append(w)

    def _load_image(self, url: str, slot: str):
        if not url:
            if slot == "small":
                self._lbl_small.hide()
            elif slot == "large":
                self._lbl_large.setText("🎵")
                self._lbl_large.setStyleSheet(
                    f"background:{_SURFACE}; border-radius:8px;"
                    f"color:{_MUTED}; font-size:28pt;"
                )
            return

        if url in self._px_cache:
            self._apply_image(self._px_cache[url], slot)
            return

        if slot == "large":
            self._cur_large = url
        elif slot == "small":
            self._cur_small = url
        else:
            self._cur_avatar = url

        self._loader.fetch(url)

    def _on_image_loaded(self, px: QPixmap, url: str):
        self._px_cache[url] = px
        if url == self._cur_large:
            self._apply_image(px, "large")
        if url == self._cur_small:
            self._apply_image(px, "small")
        if url == self._cur_avatar:
            self._apply_image(px, "avatar")

    def _apply_image(self, px: QPixmap, slot: str):
        if slot == "large":
            cropped = _crop_center(
                px.scaled(_THUMB_SIZE, _THUMB_SIZE,
                           Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation),
                _THUMB_SIZE, _THUMB_SIZE,
            )
            self._lbl_large.setPixmap(_rounded_pixmap(cropped, 8))
            self._lbl_large.setText("")
            self._lbl_large.setStyleSheet("background:transparent;")

        elif slot == "small":
            self._lbl_small.setPixmap(_circle_pixmap(px, _SMALL_SIZE))
            self._lbl_small.setText("")
            self._lbl_small.show()

        elif slot == "avatar":
            self._lbl_avatar.setPixmap(_circle_pixmap(px, _AVATAR_SIZE))
            self._lbl_avatar.setText("")
            self._lbl_avatar.setStyleSheet("background:transparent;")
