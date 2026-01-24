import threading
import pystray
from pystray import MenuItem as Item
from PIL import Image


class TkSystemTray:
    def __init__(self, appname, icon_path, on_show, on_exit):
        self.appname = appname
        self.on_show = on_show
        self.on_exit = on_exit

        self.icon = pystray.Icon(
            name=appname,
            icon=Image.open(icon_path),
            title=appname,
            menu=pystray.Menu(
                Item("Abrir Janela", self._show, default=True),
                Item("Fechar App", self._exit),
            ),
        )

        self._running = False

    def _show(self, icon=None, item=None):
        self.on_show()
        self.hide_icon()

    def _exit(self, icon=None, item=None):
        self.hide_icon()
        self.on_exit()

    def _on_click(self, icon, event):
        print(event)
        # event é uma string: 'DOUBLE_CLICK', 'LEFT_CLICK', etc.
        if event == 'DOUBLE_CLICK':
            self._show()

    def show_icon(self):
        if not self._running:
            self._running = True
            threading.Thread(target=self.icon.run, daemon=True).start()
        else:
            self.icon.visible = True

    def hide_icon(self):
        self.icon.visible = False

    def show_message(self, title, message):
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

