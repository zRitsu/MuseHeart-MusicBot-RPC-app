# MuseHeart-MusicBot RPC App

A desktop app that shows Discord Rich Presence for music bots running on the [MuseHeart-MusicBot](https://github.com/zRitsu/MuseHeart-MusicBot) source.

### Presence Preview:
[![](https://i.ibb.co/6tVbfFH/image.png)](https://i.ibb.co/6tVbfFH/image.png)

### App Preview:
[![](https://i.ibb.co/4RmDwS1G/image.png)](https://i.ibb.co/q5ZrrRv/image.png)

---

## Requirements

- Discord running on your PC
- A music bot based on [MuseHeart-MusicBot](https://github.com/zRitsu/MuseHeart-MusicBot)
- Python 3.10+ (if running from source)

---

## Installation

### Option 1 — Pre-built executable (Windows only)

Download the latest `.exe` from the [releases page](https://github.com/zRitsu/Discord-MusicBot-RPC/releases) and run it directly.

### Option 2 — Run from source

1. Download this repository as a ZIP (click **Code → Download ZIP**) and extract it, or clone it:
   ```
   git clone https://github.com/zRitsu/MuseHeart-MusicBot-RPC-app
   ```
2. Install dependencies:
   ```
   python -m pip install -r requirements.txt
   ```
3. Start the app:
   ```
   python rpc_client.py
   ```

### Option 3 — Build your own executable

Double-click `build.bat` (recommended), or run:
```
pyinstaller rpc_client.py
```
The compiled executable will be placed in the `builds/` folder.

---

## Setup

### 1. WebSocket URL

You need the WebSocket URL of the server where your music bot is running.

- **Local bot** (default `.env` settings):
  ```
  ws://localhost/ws
  ```
- **Hosted bot** (e.g. on a VPS or cloud service): the URL is shown on the bot's rendered web page.

  [![](https://i.ibb.co/n80PT0L/image.png)](https://i.ibb.co/n80PT0L/image.png)

Add the URL in the **Socket Settings** tab.

### 2. Access token

Get your RPC token from the bot using the `/rich_presence` slash command (or by mentioning the bot: `@bot richpresence`), then paste it in the **Socket Settings** tab.

### 3. Start

Click **Start Presence** — your Discord activity will update automatically while music is playing.

---

## Auto-start

You can pass `-autostart <seconds>` to launch presence automatically on startup (minimum 15 seconds):
```
python rpc_client.py -autostart 15
```
The window will minimize to the system tray and presence will start after the given delay.

---

## Customization

All settings are saved to `config.json` and can be changed through the GUI:

- **Display** — activity type (Playing / Listening / Watching / Competing), status display field, thumbnail, platform icon, guild name, queue text
- **Buttons** — listen button, playlist button, album button, Last.FM button, listen-along button, bot invite; drag-and-drop priority order
- **Blacklists** — hide presence for specific track titles, uploaders, or playlist names (separate entries with `||`)
- **Assets** — override icon URLs for loop, pause, play, stream, and idle states
- **App ID** — optionally override the Discord application ID used for presence

### Adding languages

Create a JSON file in a `langs/` folder next to the script, named after the language code (e.g. `es.json`). Any keys defined there will override or extend the built-in translations.

---

## Troubleshooting

If you run into any issues, open an [issue](https://github.com/zRitsu/Discord-MusicBot-RPC/issues) with a description of the problem and any relevant log output from the app.
