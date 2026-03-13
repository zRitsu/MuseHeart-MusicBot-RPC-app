from __future__ import annotations

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction


class QtSystemTray:
    """System tray icon using PyQt5's native QSystemTrayIcon."""

    def __init__(self, appname: str, icon_path: str, on_show, on_exit):
        self.appname = appname
        self.on_show = on_show
        self.on_exit = on_exit

        self._icon = QSystemTrayIcon(QIcon(icon_path))
        self._icon.setToolTip(appname)

        menu = QMenu()

        self._action_show = QAction("Open Window")
        self._action_show.triggered.connect(self._show)
        menu.addAction(self._action_show)

        self._action_exit = QAction("Exit")
        self._action_exit.triggered.connect(self._exit)
        menu.addAction(self._action_exit)

        self._icon.setContextMenu(menu)
        self._icon.activated.connect(self._on_activated)

    def _show(self):
        self.on_show()
        self.hide_icon()

    def _exit(self):
        self.hide_icon()
        self.on_exit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show()

    def show_icon(self):
        self._icon.show()

    def hide_icon(self):
        self._icon.hide()

    def show_message(self, title: str, message: str):
        try:
            self._icon.showMessage(title, message, QSystemTrayIcon.Information, 3000)
        except Exception:
            pass
