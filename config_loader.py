import json
import os.path

def read_config():

    base_config = {
        "language": "pt-br",
        "urls": [],
        "urls_disabled": [],
        "load_all_instances": False,
        "show_listen_button": True,
        "show_platform_icon": True,
        "show_playlist_button": True,
        "show_playlist_text": True,
        "show_playlist_name_in_button": True,
        "show_listen_along_button": False,
        "playlist_refs": True,
        "show_thumbnail": True,
        "bot_invite": True,
        "app_port": 85888,
        "dummy_app_id": 921606662467498045,
        "override_appid": False,
        "heartbeat": 30,
        "reconnect_timeout": 7,
        "enable_queue_text": True,
        "block_other_users_track": False,
        "button_order": ["listen_along_button", "listen_button", "playlist_button", "album_button"],
        "button_character_limit": 31,
        "track_blacklist": "",
        "uploader_blacklist": "",
        "playlist_blacklist": "",
        "token": "",
        "assets": {
            "loop": "https://i.ibb.co/5Mj4HjT/loop-track.gif",
            "loop_queue": "https://i.ibb.co/5Mj4HjT/loop-track.gif",
            "pause": "https://i.ibb.co/mDBMnH8/pause.png",
            "play": "https://i.ibb.co/PtFG93j/playbutton.png",
            "stream": "https://i.ibb.co/Qf9BSQb/stream.png",
            "idle": "https://i.ibb.co/6XS6qLy/music-img.png",
            "sources": {
                "deezer": "https://i.ibb.co/Wz7kJYy/deezer.png",
                "soundcloud": "https://i.ibb.co/CV6NB6w/soundcloud.png",
                "spotify": "https://i.ibb.co/3SWMXj8/spotify.png",
                "youtube": "https://i.ibb.co/LvX7dQL/yt.png",
                "applemusic": "https://i.ibb.co/Dr4hbS5/applemusic.png",
                "twitch": "https://cdn3.iconfinder.com/data/icons/popular-services-brands-vol-2/512/twitch-512.png"
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

            button_order = file_config.get("button_order", [])
            if button_order:
                file_config["button_order"] = [b for b in button_order if b in base_config["button_order"]]
                file_config["button_order"].extend([i for i in base_config["button_order"] if i not in file_config["button_order"]])

            file_config["button_order"] = file_config["button_order"]

            base_config.update(file_config)

            base_config["assets"].update(assets)
            base_config["assets"]["sources"].update(sources)

    if base_config["button_character_limit"] > 32:
        base_config["button_character_limit"] = 32

    return base_config
