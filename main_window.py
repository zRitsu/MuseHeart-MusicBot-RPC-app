from __future__ import annotations

import sys
import time
import traceback
from tkinter import TclError
from typing import TYPE_CHECKING, Literal

from PySimpleGUI import PySimpleGUI as sg
from psgtray import SystemTray
from app_version import version

if TYPE_CHECKING:
    from rpc_client import RpcClient

MLINE_KEY = '-MLINE-'+sg.WRITE_ONLY_KEY

class RPCGui:

    def __init__(self, client: RpcClient, autostart: int = 0):
        self.client = client
        self.appname = f"Discord RPC (Music Bot) v{version}"
        self.config = self.client.config
        self.ready = False

        self.log = ""

        self.langs = self.client.langs

        self.rpc_started = False

        self.window = self.get_window()
        menu = ['', ['Abrir Janela', 'Fechar App']]
        self.tray = SystemTray(menu, single_click_events=True, window=self.window, tooltip=self.appname)

        if autostart > 14:

            if self.config["urls"]:

                self.hide_to_tray()

                while True:

                    try:
                        self.start_presence()
                        break
                    except:
                        time.sleep(autostart)
                        continue

        self.window_loop()


    def get_window(self):

        theme = self.config.get("theme", "Reddit")

        sg.change_look_and_feel(theme)

        tab_config = [
            [
                sg.Frame("", [
                    [sg.Text('Tema do app:'),
                     sg.Combo(sg.theme_list(), default_value=theme, auto_size_text=True, key='theme',
                              enable_events=True)],
                    [sg.Text('Idioma da presence:'),
                     sg.Combo(list(self.langs), default_value=self.config["language"], auto_size_text=True,
                              key='language', enable_events=True)],
                    [sg.Checkbox('Exibir miniatura da música (quando disponível).',
                                 default=self.config["show_thumbnail"], key='show_thumbnail', enable_events=True)],
                    [sg.Checkbox('Exibir ícone da plataforma de música.',
                                 default=self.config["show_platform_icon"], key='show_platform_icon',
                                 enable_events=True)],
                    [sg.Checkbox('Exibir quantidade de músicas na fila (quando disponível).',
                                 default=self.config["enable_queue_text"], key='enable_queue_text', enable_events=True)],
                    [sg.Checkbox('Exibir nome da playlist no large_text da presence (quando disponível).',
                                 default=self.config["show_playlist_text"], key='show_playlist_text',
                                 enable_events=True)],
                    [sg.Checkbox('Bloquear update de status com músicas adicionadas por outros membros.',
                                 default=self.config["block_other_users_track"], key='block_other_users_track',
                                 enable_events=True)],
                    [sg.Checkbox('Carregar presence em todas as instâncias do discord (Beta).',
                                 default=self.config['load_all_instances'], key='load_all_instances', enable_events=True)],
                    [sg.Checkbox('Usar APP_ID Customizado: ',
                                 default=self.config['override_appid'], key='override_appid',
                                 enable_events=True),
                     sg.InputText(default_text=self.config["dummy_app_id"], key="dummy_app_id", enable_events=True)],
                ], expand_x=True),
            ],
            [
                sg.Frame("RPC Button Settings", [
                    [
                        sg.Frame("", [
                            [sg.Checkbox('Exibir o botão: ver/ouvir música/vídeo.',
                                         default=self.config["show_listen_button"],
                                         key='show_listen_button', enable_events=True)],
                            [sg.Checkbox('Adicionar o ID da playlist na url do botão de ver/ouvir (Youtube).',
                                         default=self.config["playlist_refs"], key='playlist_refs',
                                         enable_events=True)],
                            [sg.Checkbox(
                                'Exibir o botão: Ouvir junto via Discord (Caso disponível).',
                                default=self.config["show_listen_along_button"], key='show_listen_along_button',
                                enable_events=True)],
                            [sg.Checkbox('Exibir o botão: playlist (quando disponível).',
                                         default=self.config["show_playlist_button"], key='show_playlist_button',
                                         enable_events=True)],
                            [sg.Checkbox('Exibir botão de convite do bot (quando disponível).',
                                         default=self.config['bot_invite'], key='bot_invite', enable_events=True)],
                        ], border_width=0),
                        sg.Frame("Prioridade de botões", [
                            [
                                sg.Listbox(values=self.config["button_order"], size=(17, 5), expand_x=False,
                                           bind_return_key=True, key="button_order"),
                            ],
                            [
                                sg.Frame("", [
                                    [
                                        sg.Button("Up", key="btn_up_button_order", enable_events=True, expand_x=True),
                                        sg.Button("Down", key="btn_down_button_order", enable_events=True, expand_x=True)
                                    ],
                                ], border_width=0, expand_x=True)
                            ]
                        ])
                    ]
                ], expand_x=True),
            ],
        ]

        tab_assets = [
            [
                sg.Frame("", [
                    [sg.Text("Loop/Repetição:")],
                    [sg.InputText(default_text=self.config["assets"]["loop"], expand_x=True, key="asset_loop",
                                  enable_events=True)],
                    [sg.Text("Loop/Repetição Fila:")],
                    [sg.InputText(default_text=self.config["assets"]["loop_queue"], expand_x=True,
                                  key="asset_loop_queue", enable_events=True)],
                    [sg.Text("Tocando:")],
                    [sg.InputText(default_text=self.config["assets"]["play"], expand_x=True, key="asset_play",
                                  enable_events=True)],
                    [sg.Text("Pausa:")],
                    [sg.InputText(default_text=self.config["assets"]["pause"], expand_x=True, key="asset_pause",
                                  enable_events=True)],
                    [sg.Text("Stream/Transmissão:")],
                    [sg.InputText(default_text=self.config["assets"]["stream"], expand_x=True, key="asset_stream",
                                  enable_events=True)],
                    [sg.Text("Em espera:")],
                    [sg.InputText(default_text=self.config["assets"]["idle"], expand_x=True, key="asset_idle",
                                  enable_events=True)],
                ], expand_x=True)
            ],
        ]

        tab_urls = [
            [
                sg.Frame("", [
                    [
                        sg.Text('Token de acesso:'),
                        sg.InputText(default_text=self.config["token"], key="token", size=(73,1), disabled=True),
                        sg.Button("Colar Token", key="btn_paste_token", enable_events=True)
                    ],
                    [
                        sg.Text("Links Ativados:", size=(39, 1), font=("arial", 11), justification="center",
                                background_color="green2"),
                        sg.Text("Links Desativados:", size=(39, 1), font=("arial", 11), justification="center",
                                text_color="white", background_color="red")
                    ],
                    [
                        sg.Listbox(values=self.config["urls"], size=(30, 12), expand_x=True, key="url_list",
                                   horizontal_scroll=True, bind_return_key=True),
                        sg.Listbox(values=self.config["urls_disabled"], size=(30, 12), expand_x=True,
                                   horizontal_scroll=True, key="url_list_disabled", bind_return_key=True)
                    ],
                    [
                        sg.Button("Adicionar", key="btn_add_url", enable_events=True),
                        sg.Button("Editar", key="btn_edit_url", enable_events=True),
                        sg.Button("Remover", key="btn_remove_url", enable_events=True)
                    ]
                ], expand_x=True)
            ]
        ]

        tabgroup = [
            [
                sg.TabGroup(
                    [
                        [
                            sg.Tab('Main Settings', tab_config, element_justification='center'),
                            sg.Tab('Socket Settings', tab_urls, key="sockets_url"),
                            sg.Tab('Assets', tab_assets, element_justification='center'),
                        ]
                    ], key="main_tab"
                ),
            ],
            [
                [
                    [
                        sg.Frame("", [
                            [sg.Multiline(background_color="Black", key=MLINE_KEY, disabled=True,
                                          autoscroll=True, expand_x=True, size=(0, 6))]], expand_x=True,
                                 background_color="Black", title_color="White")
                    ]
                ]                ,
                [sg.Button("Iniciar Presence", font=('MS Sans Serif', 13, 'bold'), key="start_presence",
                           disabled=self.rpc_started), sg.Button("Parar Presence", key="stop_presence",
                                                                 disabled=not self.rpc_started,
                                                                 font=('MS Sans Serif', 13, 'bold')),
                 sg.Button("Limpar Log", font=('MS Sans Serif', 13, 'bold'), key="clear_log"),
                 sg.Button("Ocultar", key="tray", font=('MS Sans Serif', 13, 'bold')),
                 sg.Button("Fechar", key="exit", font=('MS Sans Serif', 13, 'bold')),
                 sg.Button("Salvar Alterações", font=('MS Sans Serif', 13, 'bold'), key="save_changes", visible=False)]
            ]
        ]

        return sg.Window(self.appname, tabgroup, finalize=True, enable_close_attempted_event=True)

    def update_log(self, text: str, tooltip: bool = False,
                   log_type: Literal["normal", "warning", "error", "info"] = "normal",
                   exception: Exception = None):

        if not self.ready:
            time.sleep(2)
        if exception:
            sg.popup_error(f'Ocorreu um erro!', exception, traceback.format_exc())
            log_type = "error"

        if log_type == "warning":
            self.window[MLINE_KEY].update(text + "\n", text_color_for_value='yellow', append=True)
        elif log_type == "error":
            self.tray.show_message(self.appname, f'Erro: {text}.')
            self.window[MLINE_KEY].update(text + "\n", text_color_for_value='red', append=True)
        elif log_type == "info":
            self.window[MLINE_KEY].update(text + "\n", text_color_for_value='cyan', append=True)
        else:
            self.window[MLINE_KEY].update(text + "\n", text_color_for_value='green2', append=True)

        if tooltip and self.tray.tray_icon.visible:
            self.tray.show_message()

        self.ready = True


    def update_buttons(self, enable: list = None, disable: list =None):

        if enable:
            for e in enable:
                self.window[e].update(disabled=False)

        if disable:
            for e in disable:
                self.window[e].update(disabled=True)

    def show_window(self):
        self.window.un_hide()
        self.window.bring_to_front()
        self.window.normal()

    def hide_to_tray(self):
        self.window.hide()
        self.tray.show_icon()

    def start_presence(self):

        if not self.config["urls"]:
            sg.popup_ok(f"Você deve adicionar pelo menos um link WS antes de iniciar presence!")
            self.window["sockets_url"].select()
            return

        self.client.gui = self
        try:
            self.client.get_app_instances()
        except Exception as e:
            self.update_log(repr(e), exception=e)
            return
        self.client.start_ws()
        self.rpc_started = True
        self.update_buttons(
            enable=["stop_presence"],
            disable=["start_presence", "load_all_instances", "dummy_app_id", "override_appid", "btn_paste_token"]
        )

    def window_loop(self):

        while True:

            event, values = self.window.read()

            if event in (sg.WIN_CLOSED, 'exit', sg.WIN_CLOSE_ATTEMPTED_EVENT):
                self.client.exit()
                break

            elif event == self.tray.key:

                if values[event] in ("Abrir Janela", sg.EVENT_SYSTEM_TRAY_ICON_DOUBLE_CLICKED,
                                     sg.EVENT_SYSTEM_TRAY_ICON_ACTIVATED):
                    self.show_window()

                elif values[event] == "Fechar App":
                    self.tray.hide_icon()
                    self.client.exit()
                    break

            elif event == "tray":
                self.hide_to_tray()
                self.tray.show_message(self.appname, 'Executando em segundo plano.')

            elif event == "theme":
                self.config[event] = values[event]
                self.update_data()
                self.window.close()
                self.window = self.get_window()
                self.tray.window = self.window

            elif event == "clear_log":
                self.window[MLINE_KEY].update("Log limpo com sucesso!\n", text_color_for_value='green2')

            elif event == "btn_up_button_order":

                index = self.config["button_order"].index(values["button_order"][0])

                if index == 0:
                    continue

                current = self.config["button_order"].pop(index)

                self.config["button_order"].insert(index-1, current)

                self.window['button_order'].update(values=self.config["button_order"], set_to_index=index-1)
                self.update_data()

            elif event == "btn_down_button_order":

                index = self.config["button_order"].index(values["button_order"][0])

                if index == len(self.config["button_order"])-1:
                    continue

                current = self.config["button_order"].pop(index)

                self.config["button_order"].insert(index + 1, current)

                self.window['button_order'].update(values=self.config["button_order"], set_to_index=index+1)
                self.update_data()

            elif event == "btn_paste_token":

                try:
                    token = self.window.TKroot.clipboard_get().replace("\n","").replace(" ", "")
                except TclError:
                    sg.popup_ok(f"Não há token copiado para a área de transferência.")
                    continue

                if len(token) != 50:
                    sg.popup_ok(f"O token colado não possui 50 caracteres:\n"
                                f"{' '.join(token.split())[:100]}")
                    continue

                self.config["token"] = token
                self.window["token"].update(value=token)
                self.update_data(process_rpc=False)

            elif event == "btn_add_url":

                while True:

                    try:
                        url_clipboard = self.window.TKroot.clipboard_get().replace("\n","").replace(" ", "")
                    except TclError:
                        url_clipboard = ""

                    url = sg.PopupGetText("Adicione o link do RPC.", default_text=url_clipboard)

                    if url is None:
                        break

                    url = url.replace(" ", "").replace("\n", "")

                    if not url.startswith(("ws://", "wss:/")):
                        sg.popup_ok(f"Você não inseriu um link válido!\n\nExemplo: ws://aaa.bbb.com:80/ws")

                    elif url in self.window['url_list'].Values or url in self.window['url_list_disabled'].Values:
                        sg.popup_ok(f"O link já está na lista!")

                    else:
                        self.config["urls"].append(url)
                        self.update_urls()
                        break

            elif event == "url_list":

                if not values["url_list"]:
                    continue

                url = self.config["urls"].pop(self.config["urls"].index(values["url_list"][0]))
                self.config["urls_disabled"].append(url)
                self.update_urls()

            elif event == "url_list_disabled":

                if not values["url_list_disabled"]:
                    continue

                url = self.config["urls_disabled"].pop(self.config["urls_disabled"].index(values["url_list_disabled"][0]))
                self.config["urls"].append(url)
                self.update_urls()

            elif event == "btn_edit_url":

                if not values["url_list"]:
                    sg.popup_ok(f"Selecione um link da lista de links ativados para editar!")
                    continue

                while True:

                    url = sg.PopupGetText("Edite o link do RPC.", default_text=values["url_list"][0])

                    if url is None:
                        break

                    if not url.startswith(("ws://", "wss:/")):
                        sg.popup_ok(f"Você não inseriu um link válido!\n\nExemplo: ws://aaa.bbb.com:80/ws")

                    elif url == values["url_list"][0]:
                        sg.popup_ok(f"Você deve colocar um link diferente!")

                    else:
                        self.config["urls"].remove(values["url_list"][0])
                        self.config["urls"].append(url)
                        self.update_urls()
                        break

            elif event == "btn_remove_url":
                if not values["url_list"]:
                    sg.popup_ok(f"Selecione um da lista de links ativados para remover!")
                    continue
                self.config["urls"].remove(values["url_list"][0])
                self.update_urls()

            elif event == "start_presence":
                self.start_presence()

            elif event == "stop_presence":
                self.client.close_app_instances()
                self.client.exit()
                self.update_log("RPC Finalizado!\n-----", tooltip=True)
                self.update_buttons(
                    disable=["stop_presence"],
                    enable=["start_presence", "load_all_instances", "dummy_app_id", "override_appid", "btn_paste_token"]
                )
                self.rpc_started = False

            elif event == "save_changes":
                self.update_data()

            elif event.startswith("asset_"):
                self.config["assets"][event[6:]] = values[event]
                self.window["save_changes"].update(visible=True)

            elif event in ("load_all_instances", "override_appid"):
                self.config[event] = values[event]
                self.update_data(process_rpc=False)

            elif event in self.config:
                self.config[event] = values[event]
                self.update_data()

            elif event in self.config["assets"]:
                self.config["assets"][event] = values[event]
                self.update_data()

        try:
            self.window.close()
        except:
            pass
        sys.exit(0)

    def update_urls(self):
        self.window['url_list'].update(values=self.config["urls"])
        self.window['url_list_disabled'].update(values=self.config["urls_disabled"])
        self.update_data(process_rpc=False)

    def update_data(self, process_rpc=True):

        self.client.save_json("./config.json", self.config)

        self.window["save_changes"].update(visible=False)

        if not process_rpc:
            return

        for user_id, user_data in self.client.last_data.items():

            for bot_id, bot_data in user_data.items():

                try:
                    self.client.process_data(user_id, bot_id, bot_data, refresh_timestamp=False)
                except Exception as e:
                    self.update_log(repr(e), log_type="error")
