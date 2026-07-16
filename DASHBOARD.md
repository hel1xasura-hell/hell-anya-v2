# ᴀɴʏᴀ Dashboard — setup guide

A control panel for your bot: live now-playing/queue, playback controls,
known users, a full command audit trail (who ran what, when, from Telegram
or the dashboard), raw logs, broadcast, and restart.

**How it's split, and why:** GitHub Pages only serves static files — it
can't run code or talk to your bot directly. So this ships as two halves:

1. **API** (`web/` folder) — runs *inside the same bot process* on Railway.
   It's the only thing that ever talks to Telegram/the queue/the database.
2. **Frontend** (`docs/` folder) — a static HTML/CSS/JS page you deploy to
   GitHub Pages. It logs in and calls the API over HTTPS.

Nothing here changes how the bot itself behaves — if the dashboard is
misconfigured or FastAPI fails to import, the bot still runs Telegram
commands normally.

## 1. Set environment variables on Railway

In your Railway project → your service → **Variables**, add:

| Variable | Value |
|---|---|
| `DASHBOARD_USERNAME` | your login username |
| `DASHBOARD_PASSWORD` | your login password |
| `DASHBOARD_SECRET` | a random string — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DASHBOARD_CORS_ORIGIN` | `https://<your-github-username>.github.io` (set after step 2; `*` works temporarily) |

**Do not** put real values for these in `.env.example` or commit them
anywhere in the repo — Railway env vars are the only place they should
live. Anyone with the username/password and your server URL has full
control of the bot, so treat them like any other admin password.

Railway already assigns your service a public URL and a `PORT` — the
dashboard API reuses both automatically, no extra service or cost.

Find your service's public URL under **Settings → Networking → Public
Networking** (generate a domain there if you haven't already). That URL
is your **server url** for step 3.

## 2. Deploy the frontend to GitHub Pages

1. Push this repo to GitHub (the `docs/` folder is already in it).
2. On GitHub: **Settings → Pages → Build and deployment → Source:**
   `Deploy from a branch`, branch `main`, folder `/docs`. Save.
3. GitHub gives you a URL like `https://your-username.github.io/repo-name/`.
   That's your dashboard.

## 3. Log in

Open your GitHub Pages URL and enter:
- **Server URL** — the Railway public URL from step 1 (e.g.
  `https://your-app.up.railway.app`), no trailing slash needed.
- **Username / password** — whatever you set as `DASHBOARD_USERNAME` /
  `DASHBOARD_PASSWORD`.

The server URL is remembered in your browser (not sensitive); the login
session is a token that expires after 12 hours and is cleared on logout.

## What each screen does

- **Overview** — voice engine status, total plays, queue length, uptime,
  top tracks/listeners.
- **Now playing** — current track with progress, and the pending queue.
- **Controls** — pause/resume/skip/replay/shuffle/clear/stop, volume,
  loop mode, remove-by-position, and a restart button.
- **Users** — everyone who has ever run a command, with first/last seen
  and a command count.
- **Commands** — full audit trail: timestamp, source (`telegram` or
  `dashboard`), who, and what command/action.
- **Logs** — tail of the bot's actual log file.
- **Broadcast** — sends a message into the group from the bot.

## Notes & limitations

- This bot is scoped to a single Telegram group (`ALLOWED_GROUP_ID`); the
  dashboard controls that group only.
- "Users" and "Commands" start recording from the moment this update is
  deployed — there's no historical data from before.
- The audit trail keeps the most recent 5,000 entries.
- If `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` aren't set, `/api/health`
  still responds (useful for Railway's health checks) but every other
  route returns 503 — the dashboard is effectively off.
