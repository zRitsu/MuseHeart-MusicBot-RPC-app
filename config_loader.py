import json
import os.path

def read_config():

    base_config = {
        "language": "pt-br",
        "urls": [],
        "urls_disabled": [],
        "load_all_instances": True,
        "show_guild_details": True,
        "show_listen_button": True,
        "show_playlist_button": True,
        "playlist_refs": True,
        "show_thumbnail": True,
        "bot_invite": True,
        "app_port": 85888,
        "dummy_app_id": 921606662467498045,
        "override_appid": False,
        "heartbeat": 30,
        "reconnect_timeout": 7,
        "enable_queue_text": True,
        "token": "",
        "assets": {
            "loop": "https://cdn.discordapp.com/emojis/912965656624889916.gif",
            "loop_queue": "https://i.ibb.co/5Mj4HjT/loop-track.gif",
            "pause": "https://i.ibb.co/mDBMnH8/pause.png",
            "stream": "https://i.ibb.co/Qf9BSQb/stream.png",
            "idle": "https://i.ibb.co/6XS6qLy/music-img.png",
            "sources": {
                "deezer": "https://i.ibb.co/zxpBbp8/deezer.png",
                "soundcloud": "https://i.ibb.co/CV6NB6w/soundcloud.png",
                "spotify": "https://i.ibb.co/3SWMXj8/spotify.png",
                "youtube": "https://i.ibb.co/LvX7dQL/yt.png"
            }
        }
    }

    base_config["reconnect_timeout"] = int(base_config["reconnect_timeout"])
    base_config["heartbeat"] = int(base_config["heartbeat"])

    if not os.path.isfile("./config.json"):
        with open("./config.json", "w") as f:
            f.write(json.dumps(base_config, indent=4))

    else:
        with open("./config.json") as f:

            file_config = json.load(f)

            assets = file_config.pop("assets", {})
            sources = assets.pop("sources", {})

            base_config.update(file_config)

            base_config["assets"].update(assets)
            base_config["assets"]["sources"].update(sources)

    return base_config
