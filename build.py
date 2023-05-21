import os
from cx_Freeze import setup, Executable
from rpc_client import app_version

if os.path.isfile("./icon.ico"):
    icon_file = "icon.ico"
else:
    icon_file = None

setup(
    name = "Discord RPC (MusicBot)",
    version = app_version,
    description = "Rich presence para bots relacionado a minha repo: zRitsu/disnake-LL-music-bot",
        options = {"build_exe": {
        'packages': ["os", "pystray._win32"],
        'include_files': [],
        'include_msvcr': True,
    }},
    executables = [Executable("rpc_client.py", icon=icon_file, targetName="musicbot_rpc.exe", base="Win32GUI")]
)