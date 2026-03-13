import argparse
import asyncio
import datetime
import json
import os
import pprint
import re
import socket
import sys
import tempfile
import time
import traceback
from threading import Thread
from typing import Optional, Union
from urllib.parse import quote

import aiohttp
import emoji
from PyQt5.QtWidgets import QApplication, QMessageBox
from discoIPC.ipc import DiscordIPC

from app_version import version
from config_loader import read_config, ActivityType, ActivityStatusDisplayType
from langs import langs
from rpc_gui import RPCGui

config = read_config()

_lock_socket: Optional[socket.socket] = None

def acquire_single_instance_lock() -> None:
    """
    Attempt to acquire an exclusive lock by binding to a specific port.
    If binding fails → another instance is already running.
    """
    global _lock_socket

    port = config['app_port']

    # Try IPv4 first (most common and reliable on many systems)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', port))
        _lock_socket = s
        return
    except OSError:
        pass

    # Fallback: try IPv6 localhost
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Only bind to localhost (not dual-stack wildcard)
        s.bind(('::1', port))
        _lock_socket = s
        return
    except OSError as e:
        # Both attempts failed → port is most likely in use
        show_port_in_use_message(port, e)
        sys.exit(1)


def show_port_in_use_message(port: int, exc: Exception) -> None:
    """Display error message using minimal QApplication instance."""
    # Create QApplication only when needed (avoids side-effects if called early)
    app = QApplication.instance() or QApplication(sys.argv)

    QMessageBox.critical(
        None,
        "Instance already running",
        f"Port {port} is already in use.\n"
        "Another instance of the application is likely running.\n\n"
        f"Error detail: {type(exc).__name__}: {exc}"
    )


def time_format(milliseconds: Union[int, float]) -> str:
    minutes, seconds = divmod(int(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    strings = f"{minutes:02d}:{seconds:02d}"

    if hours:
        strings = f"{hours}:{strings}"

    if days:
        strings = (f"{days} days" if days > 1 else f"{days} day") + (f", {strings}" if strings != "00:00" else "")

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
                    raise IPCError('Failed to send data to Discord via IPC.', client=self)
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

    def test_ipc_path(self, path):
        '''credits: pypresence https://github.com/qwertyquerty/pypresence/blob/master/pypresence/utils.py#L25
        Tests an IPC pipe to ensure that it actually works'''
        if sys.platform in ('win32', 'win64'):
            with open(path):
                return True
        else:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(path)
                return True

    def _get_ipc_path(self, pipe=0):
        # credits: pypresence https://github.com/qwertyquerty/pypresence/blob/master/pypresence/utils.py#L37

        ipc = f"discord-ipc-{pipe}"

        if sys.platform == 'win32':
            tempdir = r'\\?\pipe'
            paths = ['.']
        else:
            tempdir = (
                os.environ.get('XDG_RUNTIME_DIR')
                or (f"/run/user/{os.getuid()}" if os.path.exists(f"/run/user/{os.getuid()}") else tempfile.gettempdir())
            )
            paths = [re.sub(r'\/$', '', tempdir) + f'/{ipc}']

        for path in paths:
            full_path = os.path.abspath(os.path.join(tempdir, path))
            if sys.platform == 'win32' or os.path.isdir(full_path):
                for entry in os.scandir(full_path):
                    if entry.name.startswith(ipc) and os.path.exists(entry) and self.test_ipc_path(entry.path):
                        return entry.path
        return None


class IPCError(Exception):

    def __init__(self, error, client: MyDiscordIPC):
        self.error = error
        self.client = client

    def __repr__(self):
        return self.error


user_clients: dict[int, dict] = {}

valid_presence_fields = (
    "state", "details", "assets", "timestamps", "pid", "start", "end",
    "large_image", "large_text", "small_image", "small_text", "party_id",
    "party_size", "join", "spectate", "match", "buttons", "instance"
)

replaces = [
    ('&quot;', '"'), ('&amp;', '&'), ('(', '\u0028'), (')', '\u0029'),
    ('[', '【'), (']', '】'), ("  ", " "), ("*", '"'), ("_", ' '),
    ('{', '\u0028'), ('}', '\u0029'), ('`', "'"),
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
        self.last_data: dict = {}
        self.last_card_payload: dict = {}
        self.tasks: list = []
        self.main_task = None
        self.config = config
        self.langs = langs
        self.session: Optional[aiohttp.ClientSession] = None
        self.closing = False

        self.activity_type = {a.name: a.value for a in ActivityType}
        self.activity_status_display_type = {a.name: a.value for a in ActivityStatusDisplayType}

        if os.path.isdir("./langs"):
            for f in os.listdir("./langs"):
                if not f.endswith(".json"):
                    continue
                lang_data = self.load_json(f"./langs/{f}")
                lang = f[:-5]
                if lang not in self.langs:
                    self.langs[lang] = lang_data
                else:
                    self.langs[lang].update(lang_data)

        self.users_rpc: dict[int, dict[int, MyDiscordIPC]] = {}
        self.users_socket: dict[str, set] = {}
        self.bots_socket: dict[str, set] = {}

        self.gui: Optional[RPCGui] = None

        app = QApplication.instance() or QApplication(sys.argv)
        self.gui = RPCGui(self, autostart=autostart)
        self.gui.show()
        sys.exit(app.exec_())

    def load_json(self, json_file: str) -> dict:
        with open(json_file, encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, json_file: str, data: dict):
        with open(json_file, "w") as f:
            f.write(json.dumps(data, indent=4))

    def get_app_instances(self):
        """Connect to the first available Discord IPC pipe."""
        for i in range(10):
            try:
                rpc = MyDiscordIPC(str(config["dummy_app_id"]), pipe=i)
                rpc.connect()
                if not config["override_appid"]:
                    time.sleep(0.5)
                    rpc.disconnect()
            except Exception:
                continue

            user_data  = rpc.data['data']['user']
            user_id_   = int(user_data['id'])
            user       = user_data.get('username', '')
            disp_name  = user_data.get('global_name') or user_data.get('display_name') or user
            avatar     = user_data.get('avatar', '')

            user_clients[user_id_] = {"pipe": i, "user": user}
            rpc.user = user

            self.gui.update_log(f"RPC connected: {disp_name} ({user}) [{user_id_}] pipe: {i}")

            self.gui.update_user_card(
                user_id     = str(user_id_),
                avatar_hash = avatar,
                display_name = disp_name,
                username    = user,
            )
            break

        if not user_clients:
            raise Exception("No running Discord instance was detected.")

    def close_app_instances(self):
        """Clear presence on all connected pipes before disconnecting."""
        for u_data in self.users_rpc.values():
            for rpc in u_data.values():
                try:
                    rpc.clear()
                except Exception:
                    pass
                time.sleep(0.05)
                try:
                    rpc.disconnect()
                except Exception:
                    traceback.print_exc()
        self.users_rpc.clear()
        user_clients.clear()

    def get_bot_rpc(self, bot_id: int, pipe: int) -> MyDiscordIPC:
        rpc = MyDiscordIPC(str(bot_id), pipe=pipe)
        rpc.connect()
        return rpc

    def check_presence(self, user_id: int, bot_id: int):
        if not self.users_rpc.get(user_id):
            try:
                rpc = self.get_bot_rpc(bot_id, user_clients[user_id]["pipe"])
                self.users_rpc[user_id] = {bot_id: rpc}
                return
            except Exception:
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
        """Gracefully shut down: clear presence on all pipes, then cancel async tasks."""
        self.closing = True

        for u_data in list(self.users_rpc.values()):
            for rpc in list(u_data.values()):
                try:
                    rpc.clear()
                except Exception:
                    pass

        for t in self.tasks:
            loop.call_soon_threadsafe(t.cancel)
        try:
            loop.call_soon_threadsafe(self.main_task.cancel)
        except AttributeError:
            pass

    def process_data(self, user_id: int, bot_id: int, data: dict,
                     url: str = "", refresh_timestamp=True):
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

            payload["type"] = ActivityType.playing.value
            self.update(user_id, bot_id, payload, refresh_timestamp=refresh_timestamp)

        elif data['op'] == "close":
            try:
                self.users_socket[url].discard(user_id)
            except Exception:
                pass
            try:
                del self.last_data[user_id][bot_id]
            except Exception:
                pass
            self.update(user_id, bot_id, {})

        else:
            self.gui.update_log(f"unknown op: {data}", tooltip=True, log_type="warning")

    def update(self, user_id: int, bot_id: int, data: dict, refresh_timestamp=True):
        current_data = dict(data)
        current_data.pop("op", None)

        self.check_presence(user_id, bot_id)

        if not current_data:
            try:
                self.users_rpc[user_id][bot_id].clear()
            except Exception:
                pass
            return

        payload = {
            "assets": {
                "small_image": "https://i.ibb.co/qD5gvKR/cd.gif"
            },
            "timestamps": {},
            "type": data.get(
                "type",
                self.activity_type.get(
                    self.config["activity_type"],
                    ActivityType.playing.value
                )
            ),
            "status_display_type": data.get(
                "status_display_type",
                self.activity_status_display_type.get(
                    self.config["activity_status_display_type"],
                    ActivityStatusDisplayType.details.value
                )
            ),
        }

        if appname:=data.get("name"):
            payload["name"] = appname

        track = current_data.pop("track", None)
        thumb = current_data.pop("thumb", None)
        guild = current_data.pop("guild", "")
        start_time = current_data.pop(
            "start_time",
            datetime.datetime.now(datetime.timezone.utc).timestamp()
        )
        listen_along_url = current_data.pop("listen_along_invite", None)

        for d in list(current_data):
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
                    for blword in blacklist:
                        if blword and word in blword:
                            clear_presence = True

                if not clear_presence:
                    blacklist = self.config["uploader_blacklist"].lower().split("||")
                    for word in track["author"].lower().split():
                        for blword in blacklist:
                            if blword and word in blword:
                                clear_presence = True

                if not clear_presence and playlist_name:
                    blacklist = self.config["playlist_blacklist"].lower().split("||")
                    for word in playlist_name.lower().split():
                        for blword in blacklist:
                            if blword and word in blword:
                                clear_presence = True

            if clear_presence:
                try:
                    self.users_rpc[user_id][bot_id].clear()
                except Exception:
                    pass
                return

            if self.config["show_thumbnail"] and track.get("thumb"):
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
                    endtime = datetime.datetime.now(tz=datetime.timezone.utc) + \
                              datetime.timedelta(milliseconds=track["duration"] - track["position"])

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

            if (url_track := track.get("url")) and self.config["show_listen_button"]:
                if not self.config["playlist_refs"]:
                    url_track = url_track.split("&list=")[0]
                url_track = url_track.replace("www.", "")
                payload["assets"]["large_url"] = url_track
                payload["details_url"] = url_track

            state += f'👤{self.get_lang("author")}: {track["author"]}'

            playlist_url = track.get("playlist_url")
            album_url = track.get("album_url")
            album_name = track.get("album_name")
            large_image_desc = []

            if playlist_name and playlist_url:
                playlist_translation = self.get_lang("playlist")

                if self.config["show_playlist_button"]:
                    playlist_index = self.config["button_order"].index('playlist_button')
                    character_limit = (
                        self.config["button_character_limit"]
                        if emoji.emoji_count(playlist_name) < 1
                        else (self.config["button_character_limit"] - 7)
                    )

                    if not self.config["show_playlist_name_in_button"] or \
                            (playlist_name_size := len(playlist_name)) > character_limit:
                        button_dict[playlist_index] = {
                            "label": self.get_lang("view_playlist"),
                            "url": playlist_url.replace("www.", "")
                        }
                    else:
                        if (len(playlist_translation) + playlist_name_size + 2) > character_limit:
                            button_dict[playlist_index] = {
                                "label": playlist_name,
                                "url": playlist_url.replace("www.", "")
                            }
                        else:
                            button_dict[playlist_index] = {
                                "label": f"{playlist_translation}: {playlist_name}",
                                "url": playlist_url.replace("www.", "")
                            }

                elif self.config["show_playlist_text"]:
                    large_image_desc.append(f"{playlist_translation}: {playlist_name}")

            if album_url:
                album_txt = f'{self.get_lang("album")}: {album_name}'
                char_limit = self.config["button_character_limit"]

                if len(album_txt) < char_limit:
                    album_button = {"label": album_txt, "url": album_url}
                elif len(album_name) < char_limit:
                    album_button = {"label": album_name, "url": album_url}
                else:
                    album_button = {"label": album_name[:char_limit - 3] + "...", "url": album_url}

                button_dict[self.config["button_order"].index('album_button')] = album_button

                if payload["type"] != ActivityType.listening.value:
                    large_image_desc.append(f"📀{album_txt}")

            if not track["stream"] and track["source"] not in ("lastfm", "http", "local"):
                if track["source"] == "youtube":
                    if (track["author"].endswith(" - topic")
                            and not track["author"].endswith("Release - topic")
                            and not track["title"].startswith(track['author'][:-8])):
                        title_lf = track["title"]
                        author_lf = track["author"][:-8]
                    else:
                        try:
                            author_lf, title_lf = track["title"].split(" - ", maxsplit=1)
                        except ValueError:
                            title_lf = track["title"]
                            author_lf = track["author"]
                else:
                    title_lf = track["title"]
                    author_lf = track["author"]

                button_dict[self.config["button_order"].index('open_lastfm')] = {
                    "label": f"{self.get_lang('listen_on')} Last.FM",
                    "url": f"https://www.last.fm/music/{quote(author_lf.split(',')[0])}/_/{quote(title_lf)}"
                }

            try:
                if track["queue"] and self.config["enable_queue_text"]:
                    large_image_desc.append(
                        f'🎶{self.get_lang("queue").replace("{queue}", str(track["queue"]))}'
                    )
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
                button_dict[self.config["button_order"].index('listen_along_button')] = {
                    "label": self.get_lang("listen_along"), "url": listen_along_url
                }

            if lastfm_user := data.get("lastfm_user"):
                button_dict[self.config["button_order"].index('lastfm_profile')] = {
                    "label": f"Last.fm: {lastfm_user[:20]}",
                    "url": f"https://www.last.fm/user/{lastfm_user}"
                }

            if button_dict:
                button_dict = {
                    k: v for k, v in sorted(button_dict.items(), key=lambda x: x[0])[:2]
                }
                payload["buttons"] = list(button_dict.values())

            if loop_queue_txt:
                state += f" | 🔄{loop_queue_txt}"

            payload['state'] = state[:128] if state else "   "

        try:
            if track and not track.get('autoplay') and \
                    self.config["block_other_users_track"] and \
                    track["requester_id"] != user_id:
                self.users_rpc[user_id][bot_id].clear()
            else:
                self.users_rpc[user_id][bot_id].update_activity(payload)
                self.last_card_payload = {
                    "payload": dict(payload),
                    "track": dict(track) if track else None,
                    "guild": guild,
                }
                self.gui.update_presence_card(
                    payload=payload,
                    track=track,
                    app_name=appname,
                )

        except IPCError:
            used_pipes = [i["pipe"] for u, i in user_clients.items() if u != user_id]

            for i in range(12):
                if i in used_pipes:
                    continue
                try:
                    rpc = self.get_bot_rpc(bot_id, i)
                    self.users_rpc[user_id][bot_id] = rpc
                    user_clients[user_id]["pipe"] = i
                    self.update(user_id, bot_id, data, refresh_timestamp=refresh_timestamp)
                    self.gui.update_log(
                        f"RPC reconnected: {user_clients[user_id]['user']} | pipe: {i}"
                    )
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

    def get_idle_data(self, bot_id: int, data: dict) -> dict:
        data = dict(data)
        text_idle = self.get_lang("idle")

        payload = {
            "thumb": data.pop("thumb", None),
            "assets": {},
            "details": text_idle[0],
            "timestamps": {},
            "status_display_type": ActivityStatusDisplayType.name.value,
        }

        try:
            payload["timestamps"] = {
                "end": data["idle_endtime"],
                "start": data["idle_starttime"]
            }
        except KeyError:
            pass

        if len(text_idle) > 1:
            payload['state'] = text_idle[1]

        buttons = []
        public = data.pop("public", True)
        support_server = data.pop("support_server", None)

        if public and self.config["bot_invite"]:
            invite = (
                f"https://discord.com/api/oauth2/authorize?client_id={bot_id}"
                f"&permissions={data.pop('invite_permissions', 8)}"
                f"&scope=bot%20applications.commands"
            )
            buttons.append({"label": self.get_lang("invite"), "url": invite})
            if support_server:
                buttons.append({"label": self.get_lang("support_server"), "url": support_server})

        if len(buttons) < 2 and (lastfm_user := data.get("lastfm_user")):
            buttons.append({
                "label": f"Last.fm: {lastfm_user[:20]}",
                "url": f"https://www.last.fm/user/{lastfm_user}"
            })

        if buttons:
            payload["buttons"] = buttons

        return payload

    def get_lang(self, key: str) -> str:
        try:
            txt = self.langs[self.config["language"]].get(key)
            if not txt:
                txt = self.langs["en-us"].get(key)
        except KeyError:
            txt = self.langs["en-us"].get(key, key)
        return txt or key

    def clear_users_presences(self, uri: str):
        for bot_id in self.bots_socket.get(uri, []):
            for user_id in self.users_socket.get(uri, []):
                try:
                    self.users_rpc[user_id][bot_id].clear()
                except Exception:
                    continue

    async def handle_socket(self, uri: str):
        backoff = 7

        while True:
            try:
                async with self.session.ws_connect(
                    uri, heartbeat=self.config["heartbeat"], timeout=120
                ) as ws:

                    self.users_socket.setdefault(uri, set()).clear()
                    self.bots_socket.setdefault(uri, set()).clear()

                    self.gui.update_log(f"WebSocket connected: {uri}", tooltip=True)

                    await ws.send_str(json.dumps({
                        "op": "rpc_update",
                        "user_ids": list(user_clients),
                        "token": self.config["token"].replace(" ", "").replace("\n", ""),
                        "version": version,
                    }))

                    async for msg in ws:
                        try:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                except Exception:
                                    traceback.print_exc()
                                    continue

                                if not data.get('op'):
                                    print(data)
                                    continue

                                bot_id = data.pop("bot_id", None)
                                if self.config["override_appid"]:
                                    bot_id = int(self.config["dummy_app_id"])

                                bot_name = data.pop("bot_name", None)

                                if data['op'] == "disconnect":
                                    self.gui.update_log(
                                        f"op: {data['op']} | {uri} | reason: {data.get('reason')}",
                                        log_type="error"
                                    )
                                    self.closing = True
                                    try:
                                        await ws.close(code=1000, message=b"disconnect requested")
                                    except Exception:
                                        pass
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
                                    self.gui.update_log(
                                        f"op: {data['op']} | {user} {user_ws} | "
                                        f"bot: {(bot_name + ' ') if bot_name else ''}[{bot_id}] | "
                                        f"\nerror: {data.get('message')}",
                                        log_type="error"
                                    )
                                    continue

                                self.gui.update_log(
                                    f"op: {data['op']} | {user} {user_ws} | "
                                    f"bot: {(bot_name + ' ') if bot_name else ''}[{bot_id}]",
                                    log_type="info"
                                )

                                data["name"] = bot_name

                                try:
                                    self.last_data[user_ws][bot_id] = data
                                except KeyError:
                                    self.last_data[user_ws] = {bot_id: data}

                                data.pop("token", None)
                                self.process_data(user_ws, bot_id, data, url=uri)

                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.CLOSING,
                                aiohttp.WSMsgType.CLOSE,
                            ):
                                self.gui.update_log(f"Connection closed by server: {uri}")
                                if self.closing:
                                    return
                                return

                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                self.clear_users_presences(uri)
                                if self.closing:
                                    return
                                self.gui.update_log(
                                    f"Connection lost: {uri} | Reconnecting in "
                                    f"{time_format(backoff * 1000)} sec. {repr(ws.exception())}",
                                    tooltip=True, log_type="error"
                                )
                                await asyncio.sleep(backoff)
                                backoff *= 1.3

                            else:
                                self.gui.update_log(f"Unknown message type: {msg.type}", log_type="warning")

                        except Exception as e:
                            traceback.print_exc()
                            self.gui.update_log(f"Error on {uri}\n{repr(e)}.", log_type="error")

                    self.gui.update_log(
                        f"Disconnected: {uri} | Reconnecting in "
                        f"{time_format(self.config['reconnect_timeout'] * 1000)}...",
                        log_type="warning"
                    )
                    self.clear_users_presences(uri)
                    await asyncio.sleep(self.config['reconnect_timeout'])

            except (aiohttp.WSServerHandshakeError, aiohttp.ClientConnectorError):
                tm = backoff * 5
                self.gui.update_log(
                    f"Server unavailable: {uri} | Retrying in {time_format(tm * 1000)}.",
                    log_type="warning"
                )
                await asyncio.sleep(tm)
                backoff *= 2

            except Exception as e:
                traceback.print_exc()
                self.gui.update_log(f"Connection error: {uri} | {repr(e)}", tooltip=True, log_type="error")
                self.clear_users_presences(uri)
                await asyncio.sleep(60)

    async def create_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def handler(self):
        await self.create_session()
        urls = list(set(self.config["urls"]))
        self.tasks = [loop.create_task(self.handle_socket(uri)) for uri in urls]
        await asyncio.wait(self.tasks)

    def start_ws(self):
        self.main_task = asyncio.run_coroutine_threadsafe(self.handler(), loop)


if __name__ == "__main__":
    acquire_single_instance_lock()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-autostart', type=int,
        help='Auto-start presence on launch (minimum delay: 15 seconds)',
        default=0,
    )
    args = parser.parse_args()

    RpcClient(autostart=args.autostart)
