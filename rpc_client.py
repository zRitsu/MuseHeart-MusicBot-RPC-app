import asyncio
import json
import datetime
import os
import pprint
import sys
import time
import traceback
from threading import Thread
from typing import Optional
import aiohttp
from main_window import RPCGui
import tornado.web
from discoIPC.ipc import DiscordIPC
from config_loader import read_config
from langs import langs
from PySimpleGUI import PySimpleGUI as sg

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


class IPCError(Exception):

    def __init__(self, error, client: MyDiscordIPC):
        self.error = error
        self.client = client

    def __repr__(self):
        return self.error


user_clients = {}

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

    def __init__(self):
        self.last_data = {}
        self.tasks = []
        self.main_task = None
        self.config = config
        self.langs = langs
        self.session: Optional[aiohttp.ClientSession] = None

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

        self.gui = RPCGui(self)

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
                time.sleep(0.5)
                rpc.disconnect()
            except Exception:
                continue

            user_id_ = rpc.data['data']['user']['id']
            user = f"{rpc.data['data']['user']['username']}#{rpc.data['data']['user']['discriminator']}"
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

        data = dict(data)

        try:
            data.pop("op")
        except:
            pass

        self.check_presence(user_id, bot_id)

        if not data:
            try:
                self.users_rpc[user_id][bot_id].clear()
            except:
                pass
            return

        payload = {
            "assets": {
                "small_image": "https://i.ibb.co/qD5gvKR/cd.gif"
            },
            "timestamps": {}
        }

        track = data.pop("track", None)

        info = data.pop("info", None)

        thumb = data.pop("thumb", None)

        payload.update(data)

        if not payload["assets"].get("large_image"):
            payload["assets"]["large_image"] = thumb

        if info and track:

            if self.config["show_thumbnail"] and track["thumb"]:
                payload["assets"]["large_image"] = track["thumb"].replace("mqdefault", "default")

            if self.config["show_guild_details"]:
                payload['assets']['large_text'] = self.get_lang(
                    "server") + f': {info["guild"]["name"]} | ' + self.get_lang(
                    "channel") + f': #{info["channel"]["name"]} | ' + self.get_lang(
                    "listeners") + f': {info["members"]}'
            payload['details'] = track["title"]

            if track["stream"]:
                payload['assets']['small_image'] = self.config["assets"]["stream"]
                payload['assets']['small_text'] = self.get_lang("stream")

            if not track["paused"]:

                if not track["stream"]:
                    startTime = datetime.datetime.now(datetime.timezone.utc)

                    endtime = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                        milliseconds=track["duration"] - track["position"]))

                    if refresh_timestamp:
                        payload['timestamps']['end'] = int(endtime.timestamp())
                        payload['timestamps']['start'] = int(startTime.timestamp())
                    else:
                        payload['timestamps']['end'] = self.users_rpc[user_id][bot_id].last_data['timestamps']['end']
                        payload['timestamps']['start'] = self.users_rpc[user_id][bot_id].last_data['timestamps'][
                            'start']

                    player_loop = track.get('loop')

                    if player_loop:

                        if player_loop == "queue":
                            loop_text = self.get_lang('loop_queue')
                            payload['assets']['small_image'] = self.config["assets"]["loop_queue"]

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
                        try:
                            payload['assets']['small_image'] = self.config["assets"][track["source"]]
                        except KeyError:
                            pass
                        payload['assets']['small_text'] = track["source"]

                else:
                    payload['timestamps']['start'] = time.time()

                    payload['assets']['small_image'] = self.config["assets"]["stream"]
                    payload['assets']['small_text'] = "Stream"

            else:

                payload['assets']['small_image'] = self.config["assets"]["pause"]
                payload['assets']['small_text'] = self.get_lang("paused")

            state = ""

            buttons = []

            if (url := track.get("url")) and self.config["show_listen_button"]:
                if not self.config["playlist_refs"]:
                    url = url.split("&list=")[0]
                buttons.append({"label": self.get_lang("listen"), "url": url.replace("www.", "")})

            state += f'{self.get_lang("author")}: {track["author"]}'

            playlist_url = track.get("playlist_url")
            playlist_name = track.get("playlist_name")
            album_url = track.get("album_url")
            album_name = track.get("album_name")

            if self.config["show_playlist_button"]:

                if playlist_name and playlist_url:

                    if (playlist_size := len(playlist_name)) > 25:
                        state += f' | {self.get_lang("playlist")}: {playlist_name}'
                        buttons.append(
                            {"label": self.get_lang("view_playlist"), "url": playlist_url.replace("www.", "")})

                    else:

                        if playlist_size < 15:
                            playlist_name = f"Playlist: {playlist_name}"

                        buttons.append({"label": playlist_name, "url": playlist_url.replace("www.", "")})

                elif state and playlist_name:
                    state += f' | {playlist_name}'

                elif playlist_name:
                    state += f'{self.get_lang("playlist")}: {playlist_name}'

            if album_url and len(buttons) < 2:

                if (album_size := len(album_name)) > 22:
                    state += f' | {self.get_lang("album")}: {album_name}'
                    buttons.append({"label": self.get_lang("view_album"), "url": album_url.replace("www.", "")})

                else:

                    if album_size < 17:
                        album_name = f"{self.get_lang('album')}: {album_name}"

                    buttons.append({"label": album_name, "url": album_url})

            if not state:
                state = "   "

            payload['state'] = state

            payload["type"] = 3

            if buttons:
                payload["buttons"] = buttons

        try:

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
                    self.gui.update_log(f"RPC reconectado ao discord: {user_clients[user_id]['user']} | pipe: {i}")
                    self.update(user_id, bot_id, data, refresh_timestamp=refresh_timestamp)
                    return
                except:
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
        }

        if self.config["show_guild_details"]:
            payload["assets"]["large_text"] = self.get_lang("server") + f': {data["info"]["guild"]["name"]} | ' \
                                              + self.get_lang("channel") + f': #{data["info"]["channel"]["name"]} | ' \
                                              + self.get_lang("listeners") + f': {data["info"]["members"]}'

        if len(text_idle) > 1:
            payload['state'] = text_idle[1]

        buttons = []

        public = data.pop("public", True)

        if public and self.config["bot_invite"]:
            invite = f"https://discord.com/api/oauth2/authorize?client_id={bot_id}&" \
                     f"permissions={data.pop('invite_permissions', 8)}&scope=bot%20applications.commands"
            buttons.append({"label": self.get_lang("invite"), "url": invite})

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

    async def clear_users_presences(self, uri: str):

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

                async with self.session.ws_connect(uri, heartbeat=self.config["heartbeat"]) as ws:

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

                    await ws.send_str(json.dumps({"op": "rpc_update", "user_ids": list(user_clients), "version": 2.0}))

                    async for msg in ws:

                        if msg.type == aiohttp.WSMsgType.TEXT:

                            try:
                                data = json.loads(msg.data)
                            except Exception:
                                traceback.print_exc()
                                continue

                            try:
                                if not data['op']:
                                    continue
                            except:
                                continue

                            bot_id = data.pop("bot_id", None)
                            bot_name = data.pop("bot_name", None)

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

                            self.gui.update_log(f"op: {data['op']} | {user} {user_ws} | "
                                                f"bot: {(bot_name + ' ') if bot_name else ''}[{bot_id}]",
                                                log_type="info")

                            try:
                                self.last_data[user_ws][bot_id] = data
                            except KeyError:
                                self.last_data[user_ws] = {bot_id: data}

                            self.process_data(user_ws, bot_id, data)

                        elif msg.type in (aiohttp.WSMsgType.CLOSED,
                                          aiohttp.WSMsgType.CLOSING,
                                          aiohttp.WSMsgType.CLOSE):

                            self.gui.update_log(f"Conexão finalizada com o servidor: {uri}")
                            return

                        elif msg.type == aiohttp.WSMsgType.ERROR:

                            await self.clear_users_presences(uri)

                            self.gui.update_log(
                                f"Conexão perdida com o servidor: {uri} | Reconectando em {backoff} seg. {repr(ws.exception())}",
                                tooltip=True, log_type="warning")

                            await asyncio.sleep(backoff * 10)
                            backoff *= 1.3

                        else:
                            self.gui.update_log(
                                f"Unknow message type: {msg.type}",
                                log_type="warning"
                            )

                    self.gui.update_log(
                        f"Desconectado: {uri} | Nova tentativa de conexão em "
                        f"{self.config['reconnect_timeout']} segundos...",
                        log_type="warning"
                    )
                    await self.clear_users_presences(uri)
                    await asyncio.sleep(self.config['reconnect_timeout'])

            except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectorError):

                self.gui.update_log(
                    f"Servidor indisponível: {uri} | Nova tentativa de conexão em 10 minutos.",
                    log_type="warning"
                )
                await asyncio.sleep(600)

            except Exception as e:

                traceback.print_exc()
                self.gui.update_log(f"Erro na conexão: {uri} | {repr(e)}", tooltip=True, log_type="error")
                await self.clear_users_presences(uri)
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
    RpcClient()
