import json
import os.path

def read_config():

    base_config = {
        "language": "pt-br",
        "urls": [],
        "load_all_instances": True,
        "guild_icon": False,
        "show_guild_details": True,
        "show_listen_button": True,
        "show_playlist_button": True,
        "playlist_refs": True,
        "show_thumbnail": True,
        "force_large_app_asset": True,
        "assets": {
            "app": "https://cdn.discordapp.com/emojis/912965656624889916.gif",
            "loop":"https://cdn.discordapp.com/attachments/554468640942981147/925586275950534686/loop.gif",
            "loop_queue": "https://media.discordapp.net/attachments/554468640942981147/925570605506514985/loading-icon-animated-gif-3.gif",
            "pause": "https://i.ibb.co/mDBMnH8/pause.png",
            "soundcloud": "https://i.ibb.co/CV6NB6w/soundcloud.png",
            "spotify": "https://i.ibb.co/3SWMXj8/spotify.png",
            "stream": "https://i.ibb.co/Qf9BSQb/stream.png",
            "yt": "https://i.ibb.co/LvX7dQL/yt.png"
        }
    }

    if not os.path.isfile("./config.json"):
        with open("./config.json", "w") as f:
            f.write(json.dumps(base_config, indent=4))

    else:
        with open("./config.json") as f:
            base_config.update(json.load(f))

    return base_config