import asyncio
import json
import datetime
import pprint
import time
import traceback
import os
import websockets
from discoIPC.ipc import DiscordIPC


class MyDiscordIPC(DiscordIPC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = ""
        self.next = None
        self.updating = False

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


class IPCError(Exception):

    def __init__(self, error, client: MyDiscordIPC):
        self.error = error
        self.client = client

    def __repr__(self):
        return self.error


with open("config.json") as f:
    config = json.load(f)

user_clients = {}

dummy_app = "921606662467498045"

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

langs = {}


def get_thumb(url):
    if "youtube.com" in url:
        return ["yt", "Youtube"]
    if "spotify.com" in url:
        return ["spotify", "Spotify"]
    if "soundcloud.com" in url:
        return ["soundcloud", "Soundcloud"]


def fix_characters(text: str, limit=30):
    for r in replaces:
        text = text.replace(r[0], r[1])

    if len(text) > limit:
        return f"{text[:limit - 3]}..."
    return text


for f in os.listdir("./langs"):

    if not f.endswith(".json"):
        continue

    with open(f"./langs/{f}", encoding="utf-8") as file:
        langs[f[:-5]] = json.load(file)

for i in range(10):

    try:
        rpc = MyDiscordIPC(dummy_app, pipe=i)
        rpc.connect()
        time.sleep(0.5)
        rpc.disconnect()
        if not config.get("load_all_instances", True):
            break
    except:
        continue

    user_id_ = rpc.data['data']['user']['id']
    user = f"{rpc.data['data']['user']['username']}#{rpc.data['data']['user']['discriminator']}"
    user_clients[int(user_id_)] = {"pipe": i, "user": user}
    rpc.user = user
    print(f"RPC conectado: {user} [{user_id_}] pipe: {i}")

if not user_clients:
    print("Não foi detectado nenhuma instância do discord em execução.")
    time.sleep(10)
    raise Exception


class RpcClient:

    def __init__(self):

        self.lang = config["language"]

        self.users_rpc = {
            # user -> {bot: presence}
        }

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

    async def update(self, user_id: int, bot_id: int, data: dict):

        data = dict(data)

        self.check_presence(user_id, bot_id)

        if not data:
            try:
                self.users_rpc[user_id][bot_id].clear()
            except:
                pass
            return

        payload = {
            "assets": {
                "large_image": data.pop("thumb", config["assets"]["app"]).replace("mqdefault", "default"),
                "small_image": "https://i.ibb.co/qD5gvKR/cd.gif"
            },
            "timestamps": {}
        }

        track = data.pop("track", None)

        info = data.pop("info", None)

        payload.update(data)

        if info and track:

            payload['assets']['large_text'] = self.get_lang("server") + f': {info["guild"]["name"]} | ' + self.get_lang(
                "channel") + f': #{info["channel"]["name"]} | ' + self.get_lang("listeners") + f': {info["members"]}'
            payload['details'] = track["title"]

            if track["stream"]:
                payload['assets']['small_image'] = config["assets"]["stream"]
                payload['assets']['small_text'] = self.get_lang("stream")

            if not track["paused"]:

                if not track["stream"]:
                    startTime = datetime.datetime.now(datetime.timezone.utc)

                    endtime = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                        milliseconds=track["duration"] - track["position"]))

                    payload['timestamps']['end'] = int(endtime.timestamp())
                    payload['timestamps']['start'] = int(startTime.timestamp())

                    player_loop = track.get('loop')

                    if player_loop:

                        if player_loop == "queue":
                            loop_text = self.get_lang('loop_queue')
                            payload['assets']['small_image'] = config["assets"]["loop_queue"]

                        else:

                            if isinstance(player_loop, list):
                                loop_text = f"{self.get_lang('loop_text')}: {player_loop[0]}/{player_loop[1]}."
                            elif isinstance(player_loop, int):
                                loop_text = f"{self.get_lang('loop_remaining')}: {player_loop}"
                            else:
                                loop_text = self.get_lang("loop_text")

                            payload['assets']['small_image'] = config["assets"]["loop"]

                        payload['assets']['small_text'] = loop_text

                    else:

                        source_ico = get_thumb(track.get("url"))

                        if source_ico:
                            payload['assets']['small_image'] = config["assets"][source_ico[0]]
                            payload['assets']['small_text'] = source_ico[1]

                else:
                    payload['timestamps']['start'] = time.time()

                    payload['assets']['small_image'] = config["assets"]["stream"]
                    payload['assets']['small_text'] = "Stream"

            else:

                payload['assets']['small_image'] = config["assets"]["pause"]
                payload['assets']['small_text'] = self.get_lang("paused")

            state = ""

            buttons = []

            if url := track.get("url"):
                buttons.append({"label": self.get_lang("listen"), "url": url.replace("www.", "")})

            state += f'{self.get_lang("author")}: {track["author"]}'

            playlist_url = track.get("playlist_url")
            playlist_name = track.get("playlist_name")
            album_url = track.get("album_url")
            album_name = track.get("album_name")

            if not playlist_url:
                playlist_url = "https://cdn.discordapp.com/attachments/480195401543188483/802406033493852201/unknown.png"

            if playlist_name and playlist_url:

                if 'youtube.com' in playlist_url:
                    playlist_url = "https://www.youtube.com/playlist?list=" + \
                                   (playlist_url.split('?list=' if '?list=' in playlist_url else '&list='))[1]

                if (playlist_size := len(playlist_name)) > 25:
                    state += f' | {self.get_lang("playlist")}: {playlist_name}'
                    buttons.append({"label": self.get_lang("view_playlist"), "url": playlist_url.replace("www.", "")})

                else:

                    if playlist_size < 15:
                        playlist_name = f"Playlist: {playlist_name}"

                    buttons.append({"label": playlist_name, "url": playlist_url.replace("www.", "")})

            elif state and playlist_name:
                state += f' | {playlist_name}'

            elif playlist_name:
                state += f'{self.get_lang("playlist")}: {playlist_name}'

            elif album_url:

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
                    print(f"RPC reconectado ao discord: {user_clients[user_id]['user']} | pipe: {i}")
                    await self.update(user_id, bot_id, data)
                    return
                except:
                    continue

            del self.users_rpc[user_id]
            del user_clients[user_id]

    def get_lang(self, key: str) -> str:

        try:
            lang = langs[self.lang]
            txt: str = lang.get(key)
            if not txt:
                txt = langs["en-us"].get(key)
        except KeyError:
            txt = langs["en-us"].get(key)
        return txt

    async def clear_users_presences(self, users: set, bots: set):

        for bot_id in bots:
            for user_id in users:
                try:
                    self.users_rpc[user_id][bot_id].clear()
                except:
                    continue

    async def handle_socket(self, uri):

        backoff = 7

        while True:

            bots = set()
            users = set()

            try:
                async with websockets.connect(uri) as ws:

                    print(f"Websocket conectado: {uri}")

                    for i in user_clients:
                        await ws.send(json.dumps({"op": "rpc_update", "user_id": i}))

                    async for msg in ws:

                        try:
                            data = json.loads(msg)
                        except Exception:
                            traceback.print_exc()
                            continue

                        op = data.pop("op", None)

                        if not op:
                            continue

                        public = data.pop("public", True)
                        bot_id = data.pop("bot_id", None)

                        bots.add(bot_id)

                        users_ws = data.pop("users", None)

                        if not users_ws:
                            continue

                        else:
                            users_ws = [u for u in users_ws if u in user_clients]

                        try:
                            if not data["info"].get("members"):
                                data["info"]["members"] = len(users_ws)
                        except KeyError:
                            pass

                        for u_id in users_ws:

                            users.add(u_id)

                            try:
                                user = user_clients[u_id]["user"]
                            except KeyError:
                                continue

                            print(f"op: {op} | {user} [{u_id}] | bot: {bot_id}")

                            if op == "update":

                                await self.update(u_id, bot_id, data)

                            elif op == "idle":

                                text_idle = self.get_lang("idle")

                                data = {
                                    "assets": {
                                        "large_image": data.pop("thumb", config["assets"]["app"])
                                    },
                                    "details": text_idle[0],
                                }

                                if len(text_idle) > 1:
                                    data['state'] = text_idle[1]

                                if public:
                                    invite = f"https://discord.com/api/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands"

                                    data["buttons"] = [
                                        {
                                            "label": self.get_lang("invite"),
                                            "url": invite
                                        }
                                    ]

                                await self.update(u_id, bot_id, data)

                            elif op == "close":

                                try:
                                    users.remove(u_id)
                                except Exception:
                                    pass

                                await self.update(u_id, bot_id, {})

                            else:
                                print(f"unknow op: {msg.data}")


            except (websockets.ConnectionClosedError, ConnectionResetError, websockets.InvalidStatusCode) as e:
                print(f"Conexão perdida com o servidor: {uri} | Reconectando em {backoff} seg. {repr(e)}")
                await self.clear_users_presences(users, bots)
                await asyncio.sleep(backoff)
                backoff *= 1.3
            except ConnectionRefusedError:
                await asyncio.sleep(500)
            except Exception as e:
                traceback.print_exc()
                print(f"Erro na conexão: {uri} | {repr(e)}")
                await self.clear_users_presences(users, bots)
                await asyncio.sleep(60)

    async def handler(self):
        await asyncio.wait([asyncio.create_task(self.handle_socket(uri)) for uri in list(set(config["urls"]))])


asyncio.run(RpcClient().handler())
