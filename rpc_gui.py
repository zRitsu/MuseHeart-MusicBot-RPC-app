from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING, Literal

from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QInputDialog,
    QListWidgetItem, QVBoxLayout, QAbstractItemView,
)

from app_version import version
from config_loader import ActivityType, ActivityStatusDisplayType
from qt_tray import QtSystemTray
from rpc_preview_card import RpcPreviewCard
from ui.main_window import Ui_MainWindow

if TYPE_CHECKING:
    from rpc_client import RpcClient

class LogSignals(QObject):
    append_log    = pyqtSignal(str, str)
    show_tray_msg = pyqtSignal(str, str)
    update_card   = pyqtSignal(dict, object, str, str)
    clear_card    = pyqtSignal()
    set_user      = pyqtSignal(str, str, str, str)


class RPCGui(QMainWindow):

    def __init__(self, client: RpcClient, autostart: int = 0):
        super().__init__()

        self.client = client
        self.appname = f"Discord RPC (Music Bot) v{version}"
        self.config = self.client.config
        self.rpc_started = False
        self.ready = False

        self.langs = self.client.langs

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowTitle(self.appname)

        self._log_signals = LogSignals()
        self._log_signals.append_log.connect(self._append_log_slot)
        self._log_signals.show_tray_msg.connect(self._show_tray_msg_slot)
        self._log_signals.update_card.connect(self._update_card_slot)
        self._log_signals.clear_card.connect(self._clear_card_slot)
        self._log_signals.set_user.connect(self._set_user_slot)

        self._card = RpcPreviewCard(self)
        placeholder = self.ui.rpc_card_placeholder
        lay = QVBoxLayout(placeholder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._card)

        self.tray = QtSystemTray(
            appname=self.appname,
            icon_path="icon.ico",
            on_show=self.show_window,
            on_exit=self.client.exit,
        )

        self._populate_widgets()
        self._connect_signals()

        self.ready = True

        if autostart > 14 and self.config["urls"]:
            self.hide_to_tray()
            while True:
                try:
                    self.start_presence()
                    break
                except Exception:
                    time.sleep(autostart)

    def _populate_widgets(self):
        ui = self.ui
        cfg = self.config

        ui.combo_language.addItems(list(self.langs.keys()))
        idx = ui.combo_language.findText(cfg["language"])
        if idx >= 0:
            ui.combo_language.setCurrentIndex(idx)

        ui.combo_activity_type.addItems([a.name for a in ActivityType])
        idx = ui.combo_activity_type.findText(cfg["activity_type"])
        if idx >= 0:
            ui.combo_activity_type.setCurrentIndex(idx)

        ui.combo_activity_status_display_type.addItems([a.name for a in ActivityStatusDisplayType])
        idx = ui.combo_activity_status_display_type.findText(cfg["activity_status_display_type"])
        if idx >= 0:
            ui.combo_activity_status_display_type.setCurrentIndex(idx)

        ui.chk_show_thumbnail.setChecked(cfg["show_thumbnail"])
        ui.chk_show_platform_icon.setChecked(cfg["show_platform_icon"])
        ui.chk_enable_queue_text.setChecked(cfg["enable_queue_text"])
        ui.chk_show_guild_name.setChecked(cfg["show_guild_name"])
        ui.chk_show_playlist_text.setChecked(cfg["show_playlist_text"])
        ui.chk_block_other_users_track.setChecked(cfg["block_other_users_track"])
        ui.chk_override_appid.setChecked(cfg["override_appid"])
        ui.input_dummy_app_id.setText(str(cfg["dummy_app_id"]))

        ui.chk_show_listen_button.setChecked(bool(cfg.get("show_listen_button", True)))
        ui.chk_playlist_refs.setChecked(cfg["playlist_refs"])
        ui.chk_show_listen_along_button.setChecked(cfg["show_listen_along_button"])
        ui.chk_show_playlist_button.setChecked(cfg["show_playlist_button"])
        ui.chk_show_playlist_name_in_button.setChecked(cfg["show_playlist_name_in_button"])
        ui.chk_bot_invite.setChecked(cfg["bot_invite"])

        lw = ui.list_button_order
        lw.setDragDropMode(QAbstractItemView.InternalMove)
        lw.setDefaultDropAction(Qt.MoveAction)
        lw.setSelectionMode(QAbstractItemView.SingleSelection)
        lw.model().rowsMoved.connect(self._on_button_order_changed)
        lw.clear()
        for btn in cfg["button_order"]:
            lw.addItem(btn)

        ui.input_token.setText(cfg.get("token", ""))
        self._refresh_url_lists()

        assets = cfg["assets"]
        ui.input_asset_loop.setText(assets.get("loop", ""))
        ui.input_asset_loop_queue.setText(assets.get("loop_queue", ""))
        ui.input_asset_play.setText(assets.get("play", ""))
        ui.input_asset_pause.setText(assets.get("pause", ""))
        ui.input_asset_stream.setText(assets.get("stream", ""))
        ui.input_asset_idle.setText(assets.get("idle", ""))

        ui.input_track_blacklist.setText(cfg.get("track_blacklist", ""))
        ui.input_uploader_blacklist.setText(cfg.get("uploader_blacklist", ""))
        ui.input_playlist_blacklist.setText(cfg.get("playlist_blacklist", ""))

    def _connect_signals(self):
        ui = self.ui

        ui.combo_language.currentTextChanged.connect(
            lambda v: self._on_config_change("language", v))
        ui.combo_activity_type.currentTextChanged.connect(
            lambda v: self._on_config_change("activity_type", v))
        ui.combo_activity_status_display_type.currentTextChanged.connect(
            lambda v: self._on_config_change("activity_status_display_type", v))

        ui.chk_show_thumbnail.toggled.connect(
            lambda v: self._on_config_change("show_thumbnail", v))
        ui.chk_show_platform_icon.toggled.connect(
            lambda v: self._on_config_change("show_platform_icon", v))
        ui.chk_enable_queue_text.toggled.connect(
            lambda v: self._on_config_change("enable_queue_text", v))
        ui.chk_show_guild_name.toggled.connect(
            lambda v: self._on_config_change("show_guild_name", v))
        ui.chk_show_playlist_text.toggled.connect(
            lambda v: self._on_config_change("show_playlist_text", v))
        ui.chk_block_other_users_track.toggled.connect(
            lambda v: self._on_config_change("block_other_users_track", v))

        ui.chk_override_appid.toggled.connect(self._on_override_appid_toggled)
        ui.input_dummy_app_id.textChanged.connect(
            lambda v: self._on_config_change("dummy_app_id", v, process_rpc=False))

        ui.chk_show_listen_button.toggled.connect(
            lambda v: self._on_config_change("show_listen_button", v))
        ui.chk_playlist_refs.toggled.connect(
            lambda v: self._on_config_change("playlist_refs", v))
        ui.chk_show_listen_along_button.toggled.connect(
            lambda v: self._on_config_change("show_listen_along_button", v))
        ui.chk_show_playlist_button.toggled.connect(
            lambda v: self._on_config_change("show_playlist_button", v))
        ui.chk_show_playlist_name_in_button.toggled.connect(
            lambda v: self._on_config_change("show_playlist_name_in_button", v))
        ui.chk_bot_invite.toggled.connect(
            lambda v: self._on_config_change("bot_invite", v))

        ui.btn_up_button_order.clicked.connect(self._on_btn_order_up)
        ui.btn_down_button_order.clicked.connect(self._on_btn_order_down)

        ui.btn_paste_token.clicked.connect(self._on_paste_token)
        ui.btn_add_url.clicked.connect(self._on_add_url)
        ui.btn_edit_url.clicked.connect(self._on_edit_url)
        ui.btn_remove_url.clicked.connect(self._on_remove_url)
        ui.list_url_active.itemClicked.connect(self._on_url_active_clicked)
        ui.list_url_disabled.itemClicked.connect(self._on_url_disabled_clicked)

        ui.input_asset_loop.textChanged.connect(
            lambda v: self._on_asset_change("loop", v))
        ui.input_asset_loop_queue.textChanged.connect(
            lambda v: self._on_asset_change("loop_queue", v))
        ui.input_asset_play.textChanged.connect(
            lambda v: self._on_asset_change("play", v))
        ui.input_asset_pause.textChanged.connect(
            lambda v: self._on_asset_change("pause", v))
        ui.input_asset_stream.textChanged.connect(
            lambda v: self._on_asset_change("stream", v))
        ui.input_asset_idle.textChanged.connect(
            lambda v: self._on_asset_change("idle", v))

        ui.input_track_blacklist.textChanged.connect(
            lambda v: self._on_config_change("track_blacklist", v))
        ui.input_uploader_blacklist.textChanged.connect(
            lambda v: self._on_config_change("uploader_blacklist", v))
        ui.input_playlist_blacklist.textChanged.connect(
            lambda v: self._on_config_change("playlist_blacklist", v))

        ui.btn_start_presence.clicked.connect(self.start_presence)
        ui.btn_stop_presence.clicked.connect(self._on_stop_presence)
        ui.btn_clear_log.clicked.connect(self._on_clear_log)
        ui.btn_tray.clicked.connect(self.hide_to_tray)
        ui.btn_exit.clicked.connect(self._on_exit)
        ui.btn_save_changes.clicked.connect(self.update_data)

    def _on_config_change(self, key: str, value, process_rpc: bool = True):
        self.config[key] = value
        self.update_data(process_rpc=process_rpc)

    def _on_override_appid_toggled(self, checked: bool):
        self.config["override_appid"] = checked
        self.update_data(process_rpc=False)

    def _on_asset_change(self, key: str, value: str):
        self.config["assets"][key] = value
        self.ui.btn_save_changes.setVisible(True)

    def _on_btn_order_up(self):
        lw = self.ui.list_button_order
        row = lw.currentRow()
        if row <= 0:
            return
        item = lw.takeItem(row)
        lw.insertItem(row - 1, item)
        lw.setCurrentRow(row - 1)
        self.config["button_order"] = [lw.item(i).text() for i in range(lw.count())]
        self.update_data()

    def _on_btn_order_down(self):
        lw = self.ui.list_button_order
        row = lw.currentRow()
        if row < 0 or row >= lw.count() - 1:
            return
        item = lw.takeItem(row)
        lw.insertItem(row + 1, item)
        lw.setCurrentRow(row + 1)
        self.config["button_order"] = [lw.item(i).text() for i in range(lw.count())]
        self.update_data()

    def _on_button_order_changed(self):
        """Called after a drag-and-drop reorder in the button priority list."""
        lw = self.ui.list_button_order
        self.config["button_order"] = [lw.item(i).text() for i in range(lw.count())]
        self.update_data()

    def _on_paste_token(self):
        clipboard = QApplication.clipboard()
        token = clipboard.text().replace("\n", "").replace(" ", "")
        if len(token) != 50:
            QMessageBox.warning(
                self, "Token inválido",
                f"O token colado não possui 50 caracteres:\n{token[:100]}"
            )
            return
        self.config["token"] = token
        self.ui.input_token.setText(token)
        self.update_data(process_rpc=False)

    def _on_add_url(self):
        clipboard = QApplication.clipboard()
        default = clipboard.text().replace("\n", "").replace(" ", "")

        while True:
            url, ok = QInputDialog.getText(
                self, "Adicionar URL", "Digite a URL do WebSocket RPC:",
                text=default,
            )
            if not ok:
                break
            url = url.replace(" ", "").replace("\n", "")
            if not url.startswith(("ws://", "wss://")):
                QMessageBox.warning(
                    self, "URL inválida",
                    "Por favor, insira uma URL WebSocket válida.\n\nExemplo: ws://aaa.bbb.com:80/ws"
                )
            elif url in self.config["urls"] or url in self.config["urls_disabled"]:
                QMessageBox.warning(self, "Duplicata", "Esta URL já está na lista!")
            else:
                self.config["urls"].append(url)
                self._refresh_url_lists()
                self.update_data(process_rpc=False)
                break

    def _on_edit_url(self):
        lw = self.ui.list_url_active
        items = lw.selectedItems()
        if not items:
            QMessageBox.warning(self, "Nada selecionado",
                                "Selecione uma URL da lista ativa para editar.")
            return
        old_url = items[0].text()

        while True:
            new_url, ok = QInputDialog.getText(
                self, "Editar URL", "Edite a URL do WebSocket RPC:", text=old_url)
            if not ok:
                break
            if not new_url.startswith(("ws://", "wss://")):
                QMessageBox.warning(
                    self, "URL inválida",
                    "Por favor, insira uma URL WebSocket válida.\n\nExemplo: ws://aaa.bbb.com:80/ws"
                )
            elif new_url == old_url:
                QMessageBox.warning(self, "Sem alterações", "A URL deve ser diferente da atual.")
            else:
                self.config["urls"].remove(old_url)
                self.config["urls"].append(new_url)
                self._refresh_url_lists()
                self.update_data(process_rpc=False)
                break

    def _on_remove_url(self):
        lw = self.ui.list_url_active
        items = lw.selectedItems()
        if not items:
            QMessageBox.warning(self, "Nada selecionado",
                                "Selecione uma URL da lista ativa para remover.")
            return
        url = items[0].text()
        self.config["urls"].remove(url)
        self._refresh_url_lists()
        self.update_data(process_rpc=False)

    def _on_url_active_clicked(self, item: QListWidgetItem):
        """Move a URL from the active list to the disabled list."""
        url = item.text()
        self.config["urls"].remove(url)
        self.config["urls_disabled"].append(url)
        self._refresh_url_lists()
        self.update_data(process_rpc=False)

    def _on_url_disabled_clicked(self, item: QListWidgetItem):
        """Move a URL from the disabled list back to the active list."""
        url = item.text()
        self.config["urls_disabled"].remove(url)
        self.config["urls"].append(url)
        self._refresh_url_lists()
        self.update_data(process_rpc=False)

    def _on_stop_presence(self):
        self.client.close_app_instances()
        self.client.exit()
        self.update_log("RPC interrompido.\n-----", tooltip=True)
        self._set_rpc_started(False)

    def _on_clear_log(self):
        self.ui.txt_log.clear()
        self._append_log_slot("Log limpo.", "normal")

    def _on_exit(self):
        self.client.exit()
        QApplication.quit()

    def _refresh_url_lists(self):
        self.ui.list_url_active.clear()
        for url in self.config["urls"]:
            self.ui.list_url_active.addItem(url)

        self.ui.list_url_disabled.clear()
        for url in self.config["urls_disabled"]:
            self.ui.list_url_disabled.addItem(url)

    def _set_rpc_started(self, started: bool):
        self.rpc_started = started
        self.ui.btn_start_presence.setEnabled(not started)
        self.ui.btn_stop_presence.setEnabled(started)
        self.ui.chk_override_appid.setEnabled(not started)
        self.ui.input_dummy_app_id.setEnabled(not started)
        self.ui.btn_paste_token.setEnabled(not started)

    def update_log(self, text: str, tooltip: bool = False,
                   log_type: Literal["normal", "warning", "error", "info"] = "normal",
                   exception: Exception = None):
        """Thread-safe log update. Can be called from any thread."""
        if not self.ready:
            time.sleep(2)
        if exception:
            exc = traceback.format_exc()
            text = f"{text}\n{exc}"
            log_type = "error"

        self._log_signals.append_log.emit(text, log_type)

        if tooltip:
            title = self.appname
            msg = f"Erro: {repr(exception)[:30]}." if log_type == "error" else text
            self._log_signals.show_tray_msg.emit(title, msg)

    def _append_log_slot(self, text: str, log_type: str):
        """Runs on the UI thread."""
        color_map = {
            "warning": "#ffff00",
            "error": "#ff4444",
            "info": "#00ffff",
            "normal": "#00ff00",
        }
        color = color_map.get(log_type, "#00ff00")

        widget = self.ui.txt_log
        cursor = widget.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")

        widget.setTextCursor(cursor)
        widget.ensureCursorVisible()

    def _show_tray_msg_slot(self, title: str, message: str):
        self.tray.show_message(title, message)

    def _update_card_slot(self, payload: dict, track, guild: str, app_name: str):
        self._card.update_presence(payload, track, app_name)

    def _clear_card_slot(self):
        self._card.clear_presence()

    def _set_user_slot(self, user_id: str, avatar_hash: str,
                       display_name: str, username: str):
        self._card.set_user(user_id, avatar_hash, display_name, username)

    def update_presence_card(self, payload: dict, track=None,
                             guild: str = "", app_name: str = ""):
        """Thread-safe presence card update."""
        if not app_name:
            app_name = self.appname
        self._log_signals.update_card.emit(payload, track, guild, app_name)

    def clear_presence_card(self):
        """Thread-safe presence card clear."""
        self._log_signals.clear_card.emit()

    def update_user_card(self, user_id: str, avatar_hash: str,
                         display_name: str = "", username: str = ""):
        """Thread-safe user profile update on the card header."""
        self._log_signals.set_user.emit(user_id, avatar_hash, display_name, username)

    def start_presence(self):
        if not self.config["urls"]:
            QMessageBox.warning(
                self, "Sem URL Configurada",
                "Você precisa adicionar pelo menos uma URL de WebSocket antes de iniciar o RPC."
            )
            self.ui.tabWidget.setCurrentWidget(self.ui.tab_socket)
            return

        self.client.gui = self
        try:
            self.client.get_app_instances()
        except Exception as e:
            self.update_log(repr(e), exception=e)
            return

        self.client.start_ws()
        self._set_rpc_started(True)

    def update_data(self, process_rpc: bool = True):
        self.client.save_json("./config.json", self.config)
        self.ui.btn_save_changes.setVisible(False)

        if not process_rpc:
            return

        for user_id, user_data in self.client.last_data.items():
            for bot_id, bot_data in user_data.items():
                try:
                    self.client.process_data(user_id, bot_id, bot_data,
                                             refresh_timestamp=False)
                except Exception as e:
                    self.update_log(repr(e), log_type="error")

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        lp = self.client.last_card_payload
        if lp:
            self._card.update_presence(
                lp["payload"], lp.get("track"), self.appname
            )

    def hide_to_tray(self):
        self.hide()
        self.tray.show_icon()
        self.tray.show_message(self.appname, "Executando em segundo plano.")

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()
