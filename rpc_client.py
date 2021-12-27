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
    except:
        continue

    user_id = rpc.data['data']['user']['id']
    user = f"{rpc.data['data']['user']['username']}#{rpc.data['data']['user']['discriminator']}"
    user_clients[int(user_id)] = {"pipe": i, "user": user}
    rpc.user = user
    print(f"RPC conectado: {user} [{user_id}] pipe: {i}")


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

    def update(self, user_id: int, bot_id: int, data: dict):

        self.check_presence(user_id, bot_id)

        if not data:
            self.users_rpc[user_id][bot_id].clear()
            return

        payload = {
            "assets": {
                "large_image": data.pop("thumb", "app"),
                "small_image": "https://cdn.discordapp.com/attachments/480195401543188483/733507238290915388/cd.gif"
            },
            "timestamps": {}
        }

        track = data.pop("track", None)

        info = data.pop("info", None)

        payload.update(data)

        if info and track:

            payload['assets']['large_text'] = self.get_lang("server") + f': {info["guild"]["name"]} | ' + self.get_lang(
                "channel") + f': #{info["channel"]["name"]} | ' + self.get_lang("listeners") + f': {info["mmembers"]}'
            payload['details'] = track["title"]

            if track["stream"]:
                payload['assets']['small_image'] = "stream"
                payload['assets']['small_text'] = self.get_lang("stream")

            if not track["paused"]:

                if not track["stream"]:
                    startTime = datetime.datetime.now(datetime.timezone.utc)

                    endtime = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                        milliseconds=track["duration"] - track["position"]))

                    payload['timestamps']['end'] = int(endtime.timestamp())
                    payload['timestamps']['start'] = int(startTime.timestamp())

                    repeat = track.get('loop')

                    if repeat:

                        if isinstance(repeat, list):
                            repeat_string = f"{self.get_lang('loop_text')}: {repeat[0]}/{repeat[1]}."
                        elif isinstance(repeat, int):
                            repeat_string = f"{self.get_lang('loop_remaining')}: {repeat}"
                        else:
                            repeat_string = self.get_lang("loop_text")

                        payload['assets']['small_image'] = "loop"
                        payload['assets']['small_text'] = repeat_string

                    else:

                        source_ico = get_thumb(track.get("url"))

                        if source_ico:
                            payload['assets']['small_image'] = source_ico[0]
                            payload['assets']['small_text'] = source_ico[1]

                else:
                    payload['timestamps']['start'] = time.time()

                    payload['assets']['small_image'] = "stream"
                    payload['assets']['small_text'] = "Stream"

            else:

                payload['assets']['small_image'] = "pause"
                payload['assets']['small_text'] = self.get_lang("paused")

            state = ""

            buttons = []

            if track:

                if url := track.get("url"):
                    buttons.append({"label": self.get_lang("listen"), "url": url.replace("www.", "")})

                state += f'{self.get_lang("author")}: {track["author"]}'

                pl_url = track.get("playlist_url")
                pl_name = track.get("playlist_name")
                ab_url = track.get("album_url")
                ab_name = track.get("album_name")

                if not pl_url:
                    pl_url = "https://cdn.discordapp.com/attachments/480195401543188483/802406033493852201/unknown.png"

                if pl_name and pl_url:

                    if 'youtube.com' in pl_url:
                        pl_url = "https://www.youtube.com/playlist?list=" + \
                                 (pl_url.split('?list=' if '?list=' in pl_url else '&list='))[1]

                    if (pl_size := len(pl_name)) > 21:
                        state += f' | {self.get_lang("playlist")}: {pl_name}'
                        buttons.append({"label": self.get_lang("view_playlist"), "url": pl_url.replace("www.", "")})

                    else:

                        if pl_size < 15:
                            pl_name = f"Playlist: {pl_name}"

                        buttons.append({"label": pl_name, "url": pl_url.replace("www.", "")})

                elif state and pl_name:
                    state += f' | {pl_name}'

                elif pl_name:
                    state += f'{self.get_lang("playlist")}: {pl_name}'

                elif ab_url:

                    if (ab_size := len(ab_name)) > 21:
                        state += f' | {self.get_lang("album")}: {ab_name}'
                        buttons.append({"label": self.get_lang("view_album"), "url": ab_url.replace("www.", "")})

                    else:

                        if ab_size < 17:
                            ab_name = f"{self.get_lang('album')}: {ab_name}"

                        buttons.append({"label": ab_name, "url": ab_url})

            if not state:
                state = "   "

            payload['state'] = state

            if buttons:
                payload["buttons"] = buttons

        self.users_rpc[user_id][bot_id].update_activity(payload)


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

        while True:

            bots = set()
            users = set()

            try:
                async with websockets.connect(uri) as ws:

                    print(f"Websocket conectado: {uri}")

                    for i in user_clients:
                        await ws.send(json.dumps({"user_id": i}))

                    async for msg in ws:

                        try:
                            data = json.loads(msg)
                        except Exception:
                            traceback.print_exc()
                            continue

                        user_id = data.pop("user", None)
                        if not user_id:
                            continue

                        op = data.pop("op")
                        public = data.pop("public", True)
                        bot_id = data.pop("bot_id", None)
                        user = user_clients[user_id]["user"]

                        users.add(user_id)
                        bots.add(bot_id)

                        print(f"op: {op} | {user} [{user_id}] | bot: {bot_id}")

                        match op:

                            case "update":

                                self.update(user_id, bot_id, data)

                            case "idle":

                                text_idle = self.get_lang("idle")

                                data = {
                                    "assets": {
                                        "large_image": data.pop("thumb", "app")
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

                                self.update(user_id, bot_id, data)

                            case "close":

                                try:
                                    users.remove(user_id)
                                except:
                                    pass

                                self.update(user_id, bot_id, {})

                            case _:
                                print(f"unknow op: {msg.data}")


            except (websockets.ConnectionClosedError, ConnectionResetError) as e:
                print(f"Conexão perdida com o servidor: {uri} | Reconectando em 60seg. {repr(e)}")
                await self.clear_users_presences(users, bots)
                await asyncio.sleep(60)
            except ConnectionRefusedError:
                await asyncio.sleep(500)
            except Exception as e:
                traceback.print_exc()
                print(f"Erro na conexão: {uri} | {repr(e)}")
                await self.clear_users_presences(users, bots)
                await asyncio.sleep(60)

    async def handler(self):
        await asyncio.wait([asyncio.create_task(self.handle_socket(uri)) for uri in config["urls"]])

asyncio.run(RpcClient().handler())
