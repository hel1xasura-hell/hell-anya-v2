# ᴀɴʏᴀ — Private Telegram Voice Chat Music Bot

**ᴀɴʏᴀ** is a premium, single-group Telegram music bot that streams audio
directly into a group's Voice Chat, with a polished purple/black
now-playing UI, full queue management, Spotify link support, lyrics, and
an owner control panel. Built async, modular, and production-ready for
Railway.

- Bot: `@hel1xanyaa_bot`
- Stack: Python 3.11+, Pyrogram, PyTgCalls, Pillow, aiohttp

---

## Table of Contents

1. [Architecture](#architecture)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Generating a Session String](#generating-a-session-string)
6. [Running Locally](#running-locally)
7. [Railway Deployment](#railway-deployment)
8. [Commands](#commands)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## Architecture

```
anya-music-bot/
├── main.py                  # Entrypoint: startup, signal handling, graceful shutdown
├── config.py                 # Typed, validated environment configuration
├── core/
│   ├── bot.py                 # AnyaClient — Pyrogram client + service wiring
│   ├── player.py               # Playback orchestrator (queue + voice engine + db)
│   ├── queue_manager.py         # Per-chat async-safe track queue
│   ├── voice_engine.py           # PyTgCalls facade (join/play/pause/seek/volume)
│   ├── models.py                  # Track / PlaybackState / LoopMode dataclasses
│   └── announcer.py                # Wires playback events → Telegram messages
├── plugins/
│   ├── play.py                 # /play — search, resolve, queue or start
│   ├── controls.py               # pause/resume/skip/stop/end/queue/volume/...
│   ├── callbacks.py                # Inline button handlers
│   ├── lyrics.py                    # /lyrics
│   ├── settings.py                   # /settings
│   ├── help.py                        # /help
│   ├── owner.py                        # /restart /update /stats /logs /eval /broadcast
│   └── group_guard.py                   # Auto-leave unauthorised chats
├── utils/
│   ├── decorators.py             # restrict_to_group / admin_only / owner_only
│   ├── youtube.py                  # yt-dlp search & extraction
│   ├── spotify.py                    # Spotify metadata provider (abstract source layer)
│   ├── lyrics.py                       # Lyrics provider (Genius / lyrics.ovh)
│   ├── thumbnail.py                      # Now-playing card generator (Pillow)
│   ├── keyboards.py                        # Inline keyboard builders
│   ├── formatters.py                         # Duration / progress-bar helpers
│   └── logger.py                               # Rich + rotating-file logging setup
├── database/
│   ├── base.py                  # Abstract Database contract
│   ├── json_store.py              # Default JSON-file backend
│   └── __init__.py                  # get_database() factory / singleton
├── assets/{fonts,images}/    # Drop custom fonts here for premium card typography
├── cache/                     # Runtime cache (queue store, generated cards)
└── logs/                       # Rotating log files
```

**Design principles applied throughout:**

- **Single responsibility per module.** `core/` never imports from
  `plugins/`; `plugins/` never talks to PyTgCalls directly — everything
  goes through `Player`.
- **Database abstraction.** All persistence goes through the `Database`
  ABC in `database/base.py`. The shipped `JSONDatabase` backend can be
  swapped for PostgreSQL/MongoDB/etc. by writing one new class.
- **Security by construction.** `restrict_to_group`, `admin_only`, and
  `owner_only` decorators are applied uniformly; `group_guard.py`
  proactively leaves any chat that isn't `ALLOWED_GROUP_ID`.
- **No blocking calls on the event loop.** `yt-dlp` extraction runs via
  `asyncio.to_thread`; all network I/O uses `aiohttp`.

---

## Requirements

- Python **3.11+**
- `ffmpeg` installed and on `PATH` (already provided in the Docker image)
- A Telegram **bot account** (via [@BotFather](https://t.me/BotFather))
- A Telegram **user account** to act as the voice-chat "assistant" — bot
  accounts cannot join voice chats themselves, this is a Telegram platform
  restriction, not a limitation of this project
- API credentials from <https://my.telegram.org>

---

## Installation

```bash
git clone <your-private-repo-url> anya-music-bot
cd anya-music-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your real values (see [Configuration](#configuration)).

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `API_ID` | ✅ | App `api_id` from my.telegram.org |
| `API_HASH` | ✅ | App `api_hash` from my.telegram.org |
| `SESSION_STRING` | for voice | Pyrogram session string of the assistant user account |
| `OWNER_ID` | ✅ | Your numeric Telegram user ID — unrestricted access |
| `ALLOWED_GROUP_ID` | ✅ | The single group ᴀɴʏᴀ is permitted to operate in |
| `LOG_CHANNEL` | optional | Numeric chat ID for operational logs |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | optional | Enables `/play <spotify link>` |
| `GENIUS_API_TOKEN` | optional | Improves `/lyrics` accuracy |
| `YOUTUBE_COOKIES_B64` | optional | Fixes "Sign in to confirm you're not a bot" errors — see [YouTube Cookies](#youtube-cookies) below |
| `INACTIVITY_TIMEOUT_SECONDS` | optional | Auto-leave delay after silence (default `300`) |
| `DEFAULT_VOLUME` | optional | Starting volume percentage (default `100`) |
| `MAX_QUEUE_SIZE` | optional | Max tracks per queue (default `50`) |

Without `SESSION_STRING`, ᴀɴʏᴀ starts normally and text commands work, but
`/play` will report that voice playback is unavailable — this is
intentional so you can develop/test non-voice features without a full
setup.

---

## YouTube Cookies

Cloud provider IP ranges (Railway, AWS, GCP, etc.) get flagged by YouTube's
bot detection far more than home IPs, producing errors like:

```
ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies...
```

Fix it by giving yt-dlp real browser cookies. **Use a secondary/throwaway
Google account for this — not your main one** — since the account behind
the cookies is the one that could get rate-limited or flagged.

1. Log into YouTube in a normal browser with the throwaway account.
2. Install a cookie-export extension, e.g. **"Get cookies.txt LOCALLY"**
   (Chrome/Firefox). Official yt-dlp-recommended tools are listed at
   <https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp>.
3. On youtube.com, use the extension to export cookies for that domain as
   a `cookies.txt` file (Netscape format).
4. Base64-encode the file so it can safely live in an environment
   variable instead of being committed to your repo:

   ```bash
   # macOS / Linux
   base64 -i cookies.txt | tr -d '\n' > cookies_b64.txt

   # Windows PowerShell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("cookies.txt")) | Out-File cookies_b64.txt
   ```
5. Copy the contents of `cookies_b64.txt` into Railway's **Variables** tab
   as `YOUTUBE_COOKIES_B64`, then redeploy.

ᴀɴʏᴀ decodes this back into a real cookies file in `cache/` at startup
(`config.py`) and passes it to every yt-dlp call in `utils/youtube.py`.
Nothing is ever committed to git — `.gitignore` already excludes
`cache/*`.

**Cookies expire.** If the error comes back after weeks/months, re-export
and re-encode following the same steps.

---

## Generating a Session String

Voice chat streaming requires a regular Telegram **user** account (not the
bot) to join the call — this account must already be a member of
`ALLOWED_GROUP_ID`. Generate its session string with a short one-off
script using the same `API_ID` / `API_HASH`:

```python
from pyrogram import Client

api_id = 12345678
api_hash = "your_api_hash_here"

with Client("assistant_session", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
    print(app.export_session_string())
```

Run it, log in when prompted, and paste the printed string into
`SESSION_STRING`. Treat it exactly like a password.

---

## Running Locally

```bash
python main.py
```

You should see structured, colourised startup logs confirming the bot
(and, if configured, the assistant/voice engine) came online.

---

## Railway Deployment

1. Push this repository to GitHub (private repo recommended).
2. Create a new Railway project → **Deploy from GitHub repo**.
3. Railway detects `Dockerfile` automatically (`railway.json` pins the
   Dockerfile builder explicitly).
4. In the Railway dashboard, add every variable from `.env.example` under
   **Variables**.
5. Deploy. `railway.json` configures:
   - `ON_FAILURE` restart policy (up to 10 retries)
   - a container `HEALTHCHECK` in the Dockerfile
6. `Procfile` is included for compatibility with platforms/tools that read
   it (Railway itself uses `railway.json`/Dockerfile CMD).

Railway sends `SIGTERM` on redeploys; `main.py` installs signal handlers
that trigger `AnyaClient.stop()`, which cleanly leaves any active voice
chat, flushes the database to disk, and disconnects both Telegram
sessions before exit.

---

## Commands

**Playback**
`/play <query|link>` · `/pause` · `/resume` · `/skip` · `/stop` · `/end` ·
`/queue` · `/clearqueue` · `/remove <n>` · `/shuffle` · `/loop` ·
`/volume <0-200>` · `/replay` · `/seek <seconds>` · `/nowplaying`

**Info**
`/lyrics [artist - title]` · `/settings` · `/help` · `/ping`

**Owner only** (`OWNER_ID`)
`/restart` · `/update` · `/stats` · `/logs` · `/eval` · `/broadcast`

All playback-control commands and inline buttons (aside from `/play`,
`/queue`, `/nowplaying`, `/lyrics`, `/ping`) require Telegram group
administrator rank — the owner always bypasses this check.

---

## Troubleshooting

**"No Active Voice Chat Found"**
Start a Voice Chat in the group first (Group → Voice Chat), then retry
`/play`.

**`/play` says voice playback is unavailable**
`SESSION_STRING` is missing or invalid, or the assistant account isn't a
member of `ALLOWED_GROUP_ID`. Regenerate the session string and confirm
membership.

**Bot doesn't respond at all**
Confirm `ALLOWED_GROUP_ID` matches the group's actual chat ID exactly
(negative number for supergroups, e.g. `-100...`), and that the bot has
been added to that specific group.

**Thumbnails look plain / default font**
Drop a `.ttf`/`.otf` font (e.g. Poppins, Montserrat) into
`assets/fonts/`. No font is bundled by default to avoid licensing
entanglements in a redistributable repo.

**Spotify links fail to resolve**
Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. Without them,
Spotify links are rejected with a clear error rather than failing
silently.

---

## FAQ

**Can this bot be added to multiple groups?**
No — by design. `ALLOWED_GROUP_ID` binds it to exactly one group, and
`group_guard.py` makes it leave anywhere else automatically.

**Why does voice streaming need a separate user account?**
Telegram's Bot API does not permit bot accounts to join voice/group calls.
PyTgCalls works around this using an MTProto **user** session (the
"assistant"), which is standard practice across the Telegram voice-chat
bot ecosystem.

**Can I change the database backend?**
Yes — implement the `Database` ABC in `database/base.py` and update the
factory in `database/__init__.py`. No plugin code needs to change.

**Does this bot download and store full audio files?**
No. `yt-dlp` resolves a direct streamable URL that PyTgCalls streams
through `ffmpeg`; nothing is persisted to disk beyond generated
now-playing card images in `cache/`.
