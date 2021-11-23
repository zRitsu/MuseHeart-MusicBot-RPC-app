import os
import websockets
import asyncio
import traceback
from discoIPC.ipc import DiscordIPC
import json
import time
import datetime
from traceback import print_exc
import threading

with open("config.json") as f:
    config = json.load(f)

urls = list(set([u["url"] for u in config["data"]]))

rpc_clients = {}

langs = {}

for f in os.listdir("./langs"):

    if not f.endswith(".json"):
        continue

    with open(f"./langs/{f}", encoding="utf-8") as file:
        langs[f[:-5]] = json.load(file)

def get_thumb(url):

    if "youtube.com" in url:
        return ["yt", "Youtube"]
    if "spotify.com" in url:
        return ["spotify", "Spotify"]
    if "soundcloud.com" in url:
        return ["soundcloud", "Soundcloud"]

def fix_characters(text: str, limit=30):
    if len(text) > limit:
        return f"{text[:limit - 3]}..."
    return text


class RpcTest:

    def __init__(self, pipe=0):
        self.rpc = {}
        self.pipe = pipe
        self.user_id = ""
        self.user = ""
        self.time = None
        self.rpc_id = None
        self.rpc_info = {}
        self.delay = 7
        self.clients = {}
        self.loop = asyncio.get_event_loop()
        self.lang = config["language"]
        self.task = None
        self.exiting = False
        self.bot_ids = [d["bot_id"] for d in config["data"]]

    def boot(self):
        try:
            if not self.loop.is_running():
                self.task = self.loop.run_until_complete(self.connect())
                self.task = self.loop.run_forever()
            else:
                self.task = self.loop.create_task(self.connect())
        except Exception:
            traceback.print_exc()
            raise Exception

    async def destroy(self, bot_id: str):
        self.time = None
        try:
            self.rpc[bot_id].disconnect()
        except Exception:
            pass

    async def start(self):
        await self.check_rpc()

        for bot_id in self.bot_ids:
            if not self.rpc[bot_id].connected:
                try:
                    self.rpc[bot_id].connect()
                except Exception:
                    await self.destroy(bot_id)
                    del rpc_clients[self.pipe]
                    self.task.cancel()
                    self.exiting = True
                    return
                self.user_id = self.rpc[bot_id].data['data']['user']['id']
                self.user = f"{self.rpc[bot_id].data['data']['user']['username']}#{self.rpc[bot_id].data['data']['user']['discriminator']}"
                print(f"RPC conectado: {self.user} [{self.user_id}] pipe: {self.pipe} | Bot ID: {bot_id}]")

    async def check_rpc(self):

        if not self.rpc_id:
            self.rpc_id = self.bot_ids[0]

        for bot_id in self.bot_ids:
            if self.rpc.get(bot_id):
                continue
            try:
                try:
                    self.rpc[bot_id] = DiscordIPC(bot_id, pipe=self.pipe)
                except:
                    traceback.print_exc()
                    del rpc_clients[self.pipe]
                    self.task.cancel()
                    self.exiting = True
            except:
                continue

    async def teardown(self, bot_id):
        self.user_id = ""
        await self.check_rpc()
        try:
            self.rpc[bot_id].disconnect()
        except Exception as e:
            print(f"Fatal Error Type 1: {type(e)}")
            traceback.print_exc()

    def get_lang(self, key: str) -> str:

        try:
            lang = langs[self.lang]
            txt: str = lang.get(key)
            if not txt:
                txt = langs["en-us"].get(key)
        except KeyError:
            txt = langs["en-us"].get(key)
        return txt

    async def update(self, bot_id):

        await self.check_rpc()
        if not self.rpc.get(bot_id):
            try:
                await self.start()
            except:
                print_exc()
                await self.teardown(bot_id)
                return

        if not self.rpc[bot_id].connected:
            self.rpc[bot_id].connect()

        if not self.time:
            self.time = time.time()

        payload = {
            "assets": {
                "large_image": "app"
            },
            "timestamps": {}
        }

        track = self.rpc_info[bot_id].pop("track", None)

        info = self.rpc_info[bot_id].pop("info")

        if info and track:

            m = info["members"]
            
            payload['assets']['large_text'] = self.get_lang("server") + f': {info["guild"]["name"]} | ' + self.get_lang("channel") + f': #{info["channel"]["name"]} | ' + self.get_lang("listeners") + f': {m}'
            payload['details'] = track["title"]

            if track["stream"]:
                payload['assets']['small_image'] = "stream"
                payload['assets']['small_text'] = self.get_lang("stream")

            if not track["paused"]:

                if not track["stream"]:
                    startTime = datetime.datetime.now(datetime.timezone.utc)

                    endtime = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(milliseconds=track["duration"] - track["position"]))

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
                        payload['assets']['small_text'] =  repeat_string

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
                        pl_url = "https://www.youtube.com/playlist?list=" + (pl_url.split('?list=' if '?list=' in pl_url else '&list='))[1]

                    pl_title = f"Playlist: {pl_name}"
                    if len(pl_title) > 30:
                        pl_title = pl_name
                    buttons.append({"label": fix_characters(pl_title), "url": pl_url.replace("www.", "")})

                elif state and pl_name:
                    state += f' | {pl_name}'

                elif pl_name:
                    state += f'{self.get_lang("playlist")}: {pl_name}'

                elif ab_url:
                    buttons.append({"label": fix_characters(self.get_lang("album") + ab_name, 30), "url": ab_url.replace("www.", "")})

            if not state:
                state = "   "

            payload['state'] = state

            if buttons:
                payload["buttons"] = buttons

        else:
            self.rpc[bot_id].clear()
            return

        self.rpc[bot_id].update_activity(payload)

    async def connect(self):
        try:
            await self.start()
        except Exception as e:
            if not isinstance(e, FileNotFoundError):
                traceback.print_exc()
            else:
                self.task.cancel()
                self.exiting = True
                del rpc_clients[self.pipe]
            return

        if self.exiting:
            return

        for url in urls:
            self.clients[url] = self.loop.create_task(self.connect_ws(url))

    async def connect_ws(self, url):
    
        if self.exiting:
            return

        try:
            ws = await websockets.connect(url)
            a = {"user_id": self.user_id}
            await ws.send(json.dumps(a))

            while True:
                msg = await ws.recv()
                try:
                    data = json.loads(msg)
                except Exception:
                    traceback.print_exc()
                    continue
                op = data.pop("op")
                public = data.pop("public", True)
                bot_id = str(data.get("bot_id"))

                print(f"op: {op} | {self.user} [{self.user_id}] | bot: {bot_id}")

                match op:

                    case "update":
                        self.rpc_info[bot_id] = data
                        await self.update(bot_id)

                    case "idle":

                        try:
                            self.rpc_info[bot_id].clear()
                        except KeyError:
                            await self.check_rpc()

                        text_idle = self.get_lang("idle")

                        data = {
                            "assets": {
                                "large_image": "app"
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

                        try:
                            m = data["info"]["members"]
                            data['assets']['large_text'] = self.get_lang("server") + f': {data["info"]["guild"]["name"]} | ' + \
                                                           self.get_lang("channel") + f': #{data["info"]["channel"]["name"]} | ' + \
                                                           self.get_lang("listeners") + f': {m}'
                        except KeyError:
                            pass
                        self.rpc_info[bot_id] = data
                        self.rpc[bot_id].update_activity(data)

                    case "close":
                        try:
                            self.rpc[bot_id].clear()
                        except KeyError:
                            pass
                        self.rpc_info[bot_id] = {}

                    case _:
                        print(f"unknow op: {msg.data}")

        except websockets.ConnectionClosed as e:

            print(f'Conexão perdida com o servidor: {url} | Erro: {e.code} {e.reason}')

            for d in config["data"]:
                if d["url"] == url and d["bot_id"] in self.bot_ids:
                    self.rpc_info[d["bot_id"]].clear()
                    try:
                        self.rpc[d["bot_id"]].clear()
                    except:
                        continue

            if e.code == 1006:

                print(f"tentando novamente em {rpc.delay} segundos")

                await asyncio.sleep(self.delay)
                self.delay *= 2
                await self.connect()

        except Exception as e:
            if not isinstance(e, ConnectionRefusedError):
                print(f"Fatal Error Type 1: {type(e)} url: {url}")
                traceback.print_exc()
            try:
                self.clients[url].cancel()
            except:
                pass
            del self.clients[url]
            if not self.clients:
                self.loop.close()


for i in range(9):

    rpc = RpcTest(i)

    def start_rpc():
        try:
            rpc.boot()
            rpc_clients[i] = rpc
        except Exception as e:
            print(f"Fatal Error Type 3: {type(e)}")
            traceback.print_exc()
            del rpc_clients[i]
            raise Exception

    try:
        threading.Thread(target=start_rpc).start()
    except (Exception, FileNotFoundError):
        continue

while rpc_clients:
    time.sleep(15)
