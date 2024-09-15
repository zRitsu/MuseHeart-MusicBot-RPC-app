import argparse
import asyncio
import datetime
import json
import os
import pprint
import sys
import tempfile
import time
import traceback
from threading import Thread
from typing import Optional, Union
from urllib.parse import quote

import aiohttp
import emoji
import tornado.web
from PySimpleGUI import PySimpleGUI as sg
from discoIPC.ipc import DiscordIPC

from app_version import version
from config_loader import read_config, ActivityType
from langs import langs
from main_window import RPCGui

config = read_config()

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("O app de rich_presence está em execução!")


a = tornado.web.Application([(r'/', MainHandler)])

try:
    a.listen(config['app_port'])
except:
    sg.popup_ok(F"A porta {config['app_port']} está em uso!\nO app já está em execução?")
    sys.exit(0)

def time_format(milliseconds: Union[int, float]) -> str:
    minutes, seconds = divmod(int(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    strings = f"{minutes:02d}:{seconds:02d}"

    if hours:
        strings = f"{hours}:{strings}"

    if days:
        strings = (f"{days} dias" if days > 1 else f"{days} dia") + (f", {strings}" if strings != "00:00" else "")

    return strings

track_source_replaces = {
    "applemusic": "Apple Music",
    "youtubemusic": "Youtube Music",
}

class MyDiscordIPC(DiscordIPC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = ""
        self.next = None
        self.updating = False
        self.last_data = {}

    def _send(self, opcode, payload):

        encoded_payload = self._encode(opcode, payload)

        try:
            if self.platform == 'windows':
                self.socket.write(encoded_payload)
                try:
                    self.socket.flush()
                except OSError:
                    raise IPCError(f'Não foi possivel enviar dados ao discord via IPC.', client=self)
            else:
                self.socket.send(encoded_payload)
        except Exception as e:
            raise IPCError(f'Não foi possivel enviar dados ao discord via IPC | Erro: {repr(e)}.', client=self)

    def update_activity(self, activity=None):

        if activity:
            self.last_data = activity
        else:
            self.last_data.clear()

        try:
            super().update_activity(activity=activity)
        except Exception as e:
            self.last_data.clear()
            raise e

    def _get_ipc_path(self, id=0):
        # credits: pypresence https://github.com/qwertyquerty/pypresence/blob/31718fb442e563f879160c16e0215c7c1fa16f23/pypresence/utils.py#L25
        ipc = f"discord-ipc-{id}"

        if sys.platform in ('linux', 'darwin'):
            tempdir = (os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir())
            paths = ['.', 'snap.discord', 'app/com.discordapp.Discord', 'app/com.discordapp.DiscordCanary']
        elif sys.platform == 'win32':
            tempdir = r'\\?\pipe'
            paths = ['.']
        else:
            return

        for path in paths:
            full_path = os.path.abspath(os.path.join(tempdir, path))
            if sys.platform == 'win32' or os.path.isdir(full_path):
                for entry in os.scandir(full_path):
                    if entry.name.startswith(ipc) and os.path.exists(entry):
                        return entry.path

class IPCError(Exception):

    def __init__(self, error, client: MyDiscordIPC):
        self.error = error
        self.client = client

    def __repr__(self):
        return self.error


user_clients = {}

valid_presence_fields = ("state", "details", "assets", "timestamps", "pid", "start", "end", "large_image", "large_text",
                         "small_image", "small_text", "party_id", "party_size", "join", "spectate", "match", "buttons",
                         "instance")

replaces = [
    ('&quot;', '"'),
    ('&amp;', '&'),
    ('(', '\u0028'),
    (')', '\u0029'),
    ('[', '【'),
    (']', '】'),
    ("  ", " "),
    ("*", '"'),
    ("_", ' '),
    ("{", "\u0028"),
    ("}", "\u0029"),
    ("`", "'")
]


def fix_characters(text: str, limit=30):
    for r in replaces:
        text = text.replace(r[0], r[1])

    if len(text) > limit:
        return f"{text[:limit - 3]}..."
    return text


loop = asyncio.new_event_loop()

_t = Thread(target=loop.run_forever)
_t.daemon = True
_t.start()


class RpcClient:

    def __init__(self, autostart: int = 0):
        self.last_data = {}
        self.tasks = []
        self.main_task = None
        self.config = config
        self.langs = langs
        self.session: Optional[aiohttp.ClientSession] = None
        self.closing = False

        self.activity_type = {a.name: a.value for a in ActivityType}

        if os.path.isdir("./langs"):

            for f in os.listdir("./langs"):

                if not f.endswith(".json"):
                    continue

                lang_data = self.load_json(f"./langs/{f}")

                if not (lang := f[:-5]) in self.langs:
                    self.langs[lang] = lang_data
                else:
                    self.langs[lang].update(lang_data)

        self.users_rpc = {
            # user -> {bot: presence}
        }

        self.users_socket = {
            # url -> [ids]
        }

        self.bots_socket = {
            # url -> [ids]
        }

        self.gui = RPCGui(self, autostart=autostart)

    def load_json(self, json_file: str):

        with open(json_file, encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, json_file: str, data: dict):

        with open(json_file, "w") as f:
            f.write(json.dumps(data, indent=4))

    def get_app_instances(self):

        for i in range(10):

            try:
                rpc = MyDiscordIPC(str(config["dummy_app_id"]), pipe=i)
                rpc.connect()
                if not config["override_appid"]:
                    time.sleep(0.5)
                    rpc.disconnect()
            except Exception:
                continue

            user_id_ = rpc.data['data']['user']['id']
            user = f"{rpc.data['data']['user']['username']}"
            user_clients[int(user_id_)] = {"pipe": i, "user": user}
            rpc.user = user
            self.gui.update_log(f"RPC conectado: {user} [{user_id_}] pipe: {i}")
            if not self.config["load_all_instances"]:
                break

        if not user_clients:
            raise Exception("Não foi detectado nenhuma instância do discord em execução.")

    def close_app_instances(self):

        for u_id, u_data in self.users_rpc.items():
            for b_id, rpc in u_data.items():
                try:
                    rpc.disconnect()
                except:
                    traceback.print_exc()

        self.users_rpc.clear()
        user_clients.clear()

    def get_bot_rpc(self, bot_id: int, pipe: int) -> MyDiscordIPC:

        rpc = MyDiscordIPC(str(bot_id), pipe=pipe)
        rpc.connect()
        return rpc

    def check_presence(self, user_id: int, bot_id: int):

        if not (self.users_rpc.get(user_id)):
            try:
                rpc = self.get_bot_rpc(bot_id, user_clients[user_id]["pipe"])
                self.users_rpc[user_id] = {bot_id: rpc}
                return
            except:
                pass

        try:
            user_apps = self.users_rpc[user_id][bot_id]
            if not user_apps.connected:
                user_apps.connect()
        except KeyError:
            try:
                rpc = self.get_bot_rpc(bot_id, user_clients[user_id]["pipe"])
                self.users_rpc[user_id][bot_id] = rpc
            except FileNotFoundError:
                return

    def exit(self):
        for t in self.tasks:
            loop.call_soon_threadsafe(t.cancel)
        try:
            loop.call_soon_threadsafe(self.main_task.cancel)
        except AttributeError:
            pass

    def process_data(self, user_id: int, bot_id: int, data: dict, url: str = "", refresh_timestamp=True):

        data = dict(data)

        if data['op'] == "update":
            self.update(user_id, bot_id, data, refresh_timestamp=refresh_timestamp)

        elif data['op'] == "idle":

            try:
                self.last_data[user_id][bot_id] = dict(data)
            except KeyError:
                self.last_data[user_id] = {bot_id: dict(data)}

            payload = self.get_idle_data(bot_id, data)

            if self.config["override_appid"]:
                payload["assets"]["large_image"] = self.config["assets"]["idle"]

            self.update(user_id, bot_id, payload, refresh_timestamp=refresh_timestamp)

        elif data['op'] == "close":

            try:
                self.users_socket[url].remove(user_id)
            except:
                pass

            try:
                del self.last_data[user_id][bot_id]
            except:
                pass

            self.update(user_id, bot_id, {})

        else:
            self.gui.update_log(f"unknow op: {data}", tooltip=True, log_type="warning")

    def update(self, user_id: int, bot_id: int, data: dict, refresh_timestamp=True):

        current_data = dict(data)

        try:
            current_data.pop("op")
        except:
            pass

        self.check_presence(user_id, bot_id)

        if not current_data:
            try:
                self.users_rpc[user_id][bot_id].clear()
            except:
                pass
            return

        payload = {
            "assets": {
                "small_image": "https://i.ibb.co/qD5gvKR/cd.gif"
            },
            "timestamps": {},
            "type": data.get("type", self.activity_type.get(self.config["activity_type"], ActivityType.playing.value))
        }

        track = current_data.pop("track", None)
        thumb = current_data.pop("thumb", None)
        guild = current_data.pop("guild", "")
        start_time = current_data.pop("start_time", datetime.datetime.now(datetime.timezone.utc).timestamp())

        listen_along_url = current_data.pop("listen_along_invite", None)

        for d in dict(current_data):
            if d not in valid_presence_fields:
                del current_data[d]

        payload.update(current_data)

        if not payload["assets"].get("large_image"):
            payload["assets"]["large_image"] = thumb

        if track:

            playlist_name = track.get("playlist_name")

            clear_presence = False

            blacklist = self.config["track_blacklist"].lower().split("||")

            loop_queue_txt = ""

            if blacklist:
                for word in track["title"].lower().split():
                    for blacklistword in blacklist:
                        if word in blacklistword:
                            clear_presence = True

                if not clear_presence:
                    blacklist = self.config["uploader_blacklist"].lower().split("||")

                    for word in track["author"].lower().split():
                        for blacklistword in blacklist:
                            if word in blacklistword:
                                clear_presence = True

                if not clear_presence and playlist_name:
                    blacklist = self.config["playlist_blacklist"].lower().split("||")
                    for word in playlist_name.lower().split():
                        for blacklistword in blacklist:
                            if word in blacklistword:
                                clear_presence = True

            if clear_presence:
                self.users_rpc[user_id][bot_id].clear()
                return

            if self.config["show_thumbnail"] and track["thumb"]:
                payload["assets"]["large_image"] = track["thumb"].replace("mqdefault", "default")

            payload['details'] = track["title"]

            show_platform_icon = False

            if not track["paused"]:

                if track["stream"]:

                    if track["source"] == "twitch" and self.config["show_platform_icon"]:
                        payload['assets']['small_image'] = self.config["assets"]["sources"][track["source"]]
                        payload['assets']['small_text'] = "Twitch: " + self.get_lang("stream")
                    else:
                        payload['assets']['small_image'] = self.config["assets"]["stream"]
                        payload['assets']['small_text'] = self.get_lang("stream")

                    payload['timestamps']['start'] = track['duration']

                else:

                    endtime = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(milliseconds=track["duration"] - track["position"])

                    payload['timestamps']['end'] = int(endtime.timestamp())
                    payload['timestamps']['start'] = int(start_time)

                    player_loop = track.get('loop')

                    if player_loop:

                        if player_loop == "queue":
                            loop_queue_txt = self.get_lang('loop_queue')
                            show_platform_icon = True

                        else:

                            if isinstance(player_loop, list):
                                loop_text = f"{self.get_lang('loop_text')}: {player_loop[0]}/{player_loop[1]}."
                            elif isinstance(player_loop, int):
                                loop_text = f"{self.get_lang('loop_remaining')}: {player_loop}"
                            else:
                                loop_text = self.get_lang("loop_text")

                            payload['assets']['small_image'] = self.config["assets"]["loop"]

                            payload['assets']['small_text'] = loop_text
                    else:
                        show_platform_icon = True

                    if show_platform_icon:

                        if self.config["show_platform_icon"]:
                            try:
                                payload['assets']['small_image'] = self.config["assets"]["sources"][track["source"]]
                            except KeyError:
                                pass
                            payload['assets']['small_text'] = track["source"]

                        else:
                            payload['assets']['small_image'] = self.config["assets"]["play"]
                            payload['assets']['small_text'] = self.get_lang("playing")

            else:

                payload['assets']['small_image'] = self.config["assets"]["pause"]
                payload['assets']['small_text'] = self.get_lang("paused")

            state = ""

            button_dict = {}

            if (url := track.get("url")) and self.config["show_listen_button"]:
                if not self.config["playlist_refs"]:
                    url = url.split("&list=")[0]

                if self.config["show_platform_icon"]:
                    listen_text = f'{self.get_lang("listen_on")} {track_source_replaces.get(track["source"], track["source"].capitalize())}' if (track["source"] and track['source'] not in ("http", "local")) else self.get_lang("listen_music")
                else:
                    listen_text = f'{self.get_lang("listen_music")}'

                button_dict[self.config["button_order"].index('listen_button')] = {"label": listen_text, "url": url.replace("www.", "")}

            state += f'👤{self.get_lang("author")}: {track["author"]}'

            playlist_url = track.get("playlist_url")
            album_url = track.get("album_url")
            album_name = track.get("album_name")
            large_image_desc = []

            if playlist_name and playlist_url:

                playlist_translation = self.get_lang("playlist")

                if self.config["show_playlist_button"]:

                    playlist_index = self.config["button_order"].index('playlist_button')

                    character_limit = self.config["button_character_limit"] if emoji.emoji_count(
                        playlist_name) < 1 else (self.config["button_character_limit"] - 7)

                    if not self.config["show_playlist_name_in_button"] or (playlist_name_size:=len(playlist_name)) > character_limit:
                        button_dict[playlist_index] = {
                            "label": self.get_lang("view_playlist"), "url": playlist_url.replace("www.", "")}

                    else:

                        if ((len(playlist_translation) + playlist_name_size + 2)) > character_limit:
                            button_dict[playlist_index] = {
                                "label": playlist_name, "url": playlist_url.replace("www.", "")}
                        else:
                            button_dict[playlist_index] = {
                                "label": f"{playlist_translation}: {playlist_name}", "url": playlist_url.replace("www.", "")}

                elif self.config["show_playlist_text"]:
                    playlist_txt = f"{playlist_translation}: {playlist_name}"
                    large_image_desc.append(playlist_txt)

            if album_url:

                album_txt = f'{self.get_lang("album")}: {album_name}'

                if len(album_txt) < self.config["button_character_limit"]:
                    album_button = {"label": album_txt, "url": album_url}
                elif len(album_name) < self.config["button_character_limit"]:
                    album_button = {"label": album_name, "url": album_url}
                else:
                    album_button = {"label": (album_name[:self.config["button_character_limit"]-3] + "..."), "url": album_url}

                button_dict[self.config["button_order"].index('album_button')] = album_button

                if payload["type"] != ActivityType.listening.value:
                    large_image_desc.append(f"📀{album_txt}")

            if not track["stream"] and (track["source"] not in ("lastfm", "http", "local")):

                if track["source"] == "youtube":
                    if track["author"].endswith(" - topic") and not track["author"].endswith(
                            "Release - topic") and not track["title"].startswith(track['author'][:-8]):
                        title = track["title"]
                        author = track["author"][:-8]
                    else:
                        try:
                            author, title = track["title"].split(" - ", maxsplit=1)
                        except ValueError:
                            title = track["title"]
                            author = track["author"]
                else:
                    title = track["title"]
                    author = track["author"]

                button_dict[self.config["button_order"].index('open_lastfm')] = {
                    "label": f"{self.get_lang('listen_on')} Last.FM",
                    "url": f"https://www.last.fm/music/{quote(author.split(',')[0])}/_/{quote(title)}"
                }

            try:
                if track["queue"] and self.config["enable_queue_text"]:
                    large_image_desc.append(f'🎶{self.get_lang("queue").replace("{queue}", str(track["queue"]))}')
            except KeyError:
                pass

            if guild and self.config['show_guild_name']:
                large_image_desc.append(f"🌐{self.get_lang('server')}: {guild}")

            try:
                if track["247"]:
                    large_image_desc.append("⏰24/7")
            except KeyError:
                pass

            try:
                if track["autoplay"]:
                    state += f" | 👍{self.get_lang('recommended')}"
            except KeyError:
                pass

            if large_image_desc:
                payload['assets']['large_text'] = " | ".join(large_image_desc)

            if self.config['show_listen_along_button'] and listen_along_url:
                button_dict[self.config["button_order"].index('listen_along_button')] = {"label": self.get_lang("listen_along"), "url": listen_along_url}

            if lastfm_user:=data.get("lastfm_user"):
                button_dict[self.config["button_order"].index('lastfm_profile')] = {"label": f"Last.fm: {lastfm_user[:20]}", "url": f"https://www.last.fm/user/{lastfm_user}"}

            if button_dict:

                button_dict = {key: value for key, value in sorted(button_dict.items(), key=lambda k: k)[:2]}


                payload["buttons"] = [v for v in button_dict.values()]

            if loop_queue_txt:
                state += f" | 🔄{loop_queue_txt}"

            if not state:
                payload['state'] = "   "
            else:
                payload['state'] = state[:128]

        try:

            if track and not track.get('autoplay') and (self.config["block_other_users_track"] and track["requester_id"] != user_id):
                self.users_rpc[user_id][bot_id].clear()
            else:
                self.users_rpc[user_id][bot_id].update_activity(payload)

        except IPCError:

            used_pipes = [i["pipe"] for u, i in user_clients.items() if u != user_id]

            for i in range(12):

                if i in used_pipes:
                    continue

                try:
                    rpc = self.get_bot_rpc(bot_id, i)
                    rpc.connect()
                    self.users_rpc[user_id][bot_id] = rpc
                    user_clients[user_id]["pipe"] = i
                    self.update(user_id, bot_id, data, refresh_timestamp=refresh_timestamp)
                    self.gui.update_log(f"RPC reconectado ao discord: {user_clients[user_id]['user']} | pipe: {i}")
                    return
                except Exception:
                    traceback.print_exc()
                    continue

            del self.users_rpc[user_id]
            del user_clients[user_id]

        except Exception as e:
            traceback.print_exc()
            self.gui.update_log(repr(e), exception=e)
            pprint.pprint(payload)

    def get_idle_data(self, bot_id: int, data: dict):

        data = dict(data)

        text_idle = self.get_lang("idle")

        payload = {
            "thumb": data.pop("thumb", None),
            "assets": {},
            "details": text_idle[0],
            "timestamps": {}
        }

        try:
            payload["timestamps"] = {"end": data["idle_endtime"], "start": data["idle_starttime"]}
        except KeyError:
            pass

        if len(text_idle) > 1:
            payload['state'] = text_idle[1]

        buttons = []

        public = data.pop("public", True)
        support_server = data.pop("support_server", None)

        if public and self.config["bot_invite"]:
            invite = f"https://discord.com/api/oauth2/authorize?client_id={bot_id}&" \
                     f"permissions={data.pop('invite_permissions', 8)}&scope=bot%20applications.commands"
            buttons.append({"label": self.get_lang("invite"), "url": invite})
            if support_server:
                buttons.append({"label": self.get_lang("support_server"), "url": support_server})

        if len(buttons) < 2 and (lastfm_user := data.get("lastfm_user")):
            buttons.append({"label": f"Last.fm: {lastfm_user[:20]}", "url": f"https://www.last.fm/user/{lastfm_user}"})

        if buttons:
            payload["buttons"] = buttons

        return payload

    def get_lang(self, key: str) -> str:

        try:
            lang = self.langs[self.config["language"]]
            txt: str = lang.get(key)
            if not txt:
                txt = self.langs["en-us"].get(key)
        except KeyError:
            txt = self.langs["en-us"].get(key)
        return txt

    def clear_users_presences(self, uri: str):

        for bot_id in self.bots_socket[uri]:
            for user_id in self.users_socket[uri]:
                try:
                    self.users_rpc[user_id][bot_id].clear()
                except:
                    continue

    async def handle_socket(self, uri):

        backoff = 7

        while True:

            try:

                async with self.session.ws_connect(uri, heartbeat=self.config["heartbeat"], timeout=120) as ws:

                    try:
                        self.users_socket[uri].clear()
                    except:
                        pass

                    try:
                        self.bots_socket[uri].clear()
                    except:
                        pass

                    self.bots_socket[uri] = set()
                    self.users_socket[uri] = set()

                    self.gui.update_log(f"Websocket conectado: {uri}", tooltip=True)

                    await ws.send_str(
                        json.dumps(
                            {
                                "op": "rpc_update",
                                "user_ids": list(user_clients),
                                "token": self.config["token"].replace(" ", "").replace("\n", ""),
                                "version": version
                            }
                        )
                    )

                    async for msg in ws:

                        try:

                            if msg.type == aiohttp.WSMsgType.TEXT:

                                try:
                                    data = json.loads(msg.data)
                                except Exception:
                                    traceback.print_exc()
                                    continue

                                try:
                                    if not data['op']:
                                        print(data)
                                        continue
                                except:
                                    traceback.print_exc()
                                    continue

                                bot_id = data.pop("bot_id", None)

                                if self.config["override_appid"]:
                                    bot_id = int(self.config["dummy_app_id"])

                                bot_name = data.pop("bot_name", None)

                                if data['op'] == "disconnect":
                                    self.gui.update_log(f"op: {data['op']} | {uri} | reason: {data.get('reason')}",
                                                        log_type="error")
                                    self.closing = True
                                    await ws.close()
                                    return

                                if bot_id:
                                    try:
                                        self.bots_socket[uri].add(bot_id)
                                    except TypeError:
                                        for i in bot_id:
                                            self.bots_socket[uri].add(i)

                                user_ws = data.pop("user", None)

                                if not user_ws:
                                    continue

                                self.users_socket[uri].add(user_ws)

                                try:
                                    user = user_clients[user_ws]["user"]
                                except KeyError:
                                    continue

                                if data['op'] == "exception":
                                    self.gui.update_log(f"op: {data['op']} | {user} {user_ws} | "
                                                        f"bot: {(bot_name + ' ') if bot_name else ''}[{bot_id}] | "
                                                        f"\nerror: {data.get('message')}",
                                                        log_type="error")
                                    continue

                                self.gui.update_log(f"op: {data['op']} | {user} {user_ws} | "
                                                    f"bot: {(bot_name + ' ') if bot_name else ''}[{bot_id}]",
                                                    log_type="info")

                                try:
                                    self.last_data[user_ws][bot_id] = data
                                except KeyError:
                                    self.last_data[user_ws] = {bot_id: data}

                                try:
                                    del data["token"]
                                except KeyError:
                                    pass

                                self.process_data(user_ws, bot_id, data, url=uri)

                            elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                              aiohttp.WSMsgType.CLOSING,
                                              aiohttp.WSMsgType.CLOSE):

                                self.gui.update_log(f"Conexão finalizada com o servidor: {uri}")
                                return

                            elif msg.type == aiohttp.WSMsgType.ERROR:

                                self.clear_users_presences(uri)

                                if self.closing:
                                    return

                                self.gui.update_log(
                                    f"Conexão perdida com o servidor: {uri} | Reconectando em {time_format(backoff)} seg. {repr(ws.exception())}",
                                    tooltip=True, log_type="error")

                                await asyncio.sleep(backoff)
                                backoff *= 1.3

                            else:
                                self.gui.update_log(
                                    f"Unknow message type: {msg.type}",
                                    log_type="warning"
                                )

                        except Exception as e:
                            traceback.print_exc()
                            self.gui.update_log(
                                f"Ocorreu um erro no link: {uri}\n{repr(e)}.",
                                log_type="error"
                            )

                    self.gui.update_log(
                        f"Desconectado: {uri} | Nova tentativa de conexão em "
                        f"{time_format(self.config['reconnect_timeout']*1000)}...",
                        log_type="warning"
                    )
                    self.clear_users_presences(uri)
                    await asyncio.sleep(self.config['reconnect_timeout'])

            except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectorError):

                tm = backoff * 5

                self.gui.update_log(
                    f"Servidor indisponível: {uri} | Nova tentativa de conexão em {time_format(tm*1000)}.",
                    log_type="warning"
                )
                await asyncio.sleep(tm)
                backoff *= 2

            except Exception as e:

                traceback.print_exc()
                self.gui.update_log(f"Erro na conexão: {uri} | {repr(e)}", tooltip=True, log_type="error")
                self.clear_users_presences(uri)
                await asyncio.sleep(60)

    async def create_session(self):

        if not self.session:
            self.session = aiohttp.ClientSession()

    async def handler(self):

        await self.create_session()

        self.tasks = [loop.create_task(self.handle_socket(uri)) for uri in list(set(self.config["urls"]))]
        await asyncio.wait(self.tasks)

    def start_ws(self):
        self.main_task = asyncio.run_coroutine_threadsafe(self.handler(), loop)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('-autostart', type=int, help='Iniciar presence automaticamente (tempo mínimo: 15)', default=0)
    args = parser.parse_args()

    RpcClient(autostart=args.autostart)
