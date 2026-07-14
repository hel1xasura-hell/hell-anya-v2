"""
plugins/play.py
================
Implements ``/play`` — the single entry point for queuing music, whether
from a search phrase, a direct YouTube URL, or a Spotify track link.

UX contract: exactly one status message is sent ("🔍 Processing your
query...") and then *edited* in place through every subsequent stage, per
the project's "never spam multiple messages" requirement.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from core.models import SourceType, Track
from core.voice_engine import NoActiveVoiceChatError
from utils.decorators import restrict_to_group
from utils.formatters import format_duration
from utils.spotify import SpotifyLookupError, SpotifyNotConfiguredError, spotify_provider
from utils.thumbnail import generate_now_playing_card
from utils.youtube import TrackNotFoundError, search_or_resolve

logger = logging.getLogger(__name__)


async def _resolve_query(query: str) -> tuple[Track, str]:
    """Resolve a raw ``/play`` argument into a :class:`Track` skeleton.

    Returns ``(track_without_requester_info, source_label)``. The caller
    fills in ``requested_by_*`` before enqueueing.
    """

    if spotify_provider.is_spotify_url(query):
        try:
            meta = await spotify_provider.fetch_track_metadata(query)
        except SpotifyNotConfiguredError as exc:
            raise TrackNotFoundError(str(exc)) from exc
        except SpotifyLookupError as exc:
            raise TrackNotFoundError(f"Could not read that Spotify link: {exc}") from exc

        youtube_result = await search_or_resolve(f"{meta.artist} {meta.title} audio")
        track = Track(
            title=meta.title,
            artist=meta.artist,
            duration_seconds=meta.duration_seconds or youtube_result.duration_seconds,
            stream_url=youtube_result.stream_url,
            thumbnail_url=meta.album_art_url or youtube_result.thumbnail_url,
            webpage_url=meta.spotify_url,
            requested_by_id=0,
            requested_by_name="",
            source=SourceType.SPOTIFY,
            http_headers=youtube_result.http_headers,
        )
        return track, "Spotify"

    youtube_result = await search_or_resolve(query)
    track = Track(
        title=youtube_result.title,
        artist=youtube_result.artist,
        duration_seconds=youtube_result.duration_seconds,
        stream_url=youtube_result.stream_url,
        thumbnail_url=youtube_result.thumbnail_url,
        webpage_url=youtube_result.webpage_url,
        requested_by_id=0,
        requested_by_name="",
        source=SourceType.DIRECT_URL if query.startswith("http") else SourceType.YOUTUBE,
        http_headers=youtube_result.http_headers,
    )
    return track, "YouTube"


@Client.on_message(filters.command("play") & filters.group)
@restrict_to_group
async def play_command(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text(
            "🎵 Usage: /play <song name or YouTube/Spotify link>",
            quote=True,
        )
        return

    query = message.text.split(None, 1)[1].strip()
    status = await message.reply_text("🔍 Processing your query...", quote=True)

    try:
        player = client.require_player()
    except RuntimeError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return

    try:
        track, source_label = await _resolve_query(query)
    except TrackNotFoundError as exc:
        await status.edit_text(f"❌ Couldn't find that track.\n`{exc}`")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error resolving query %r", query)
        await status.edit_text("⚠️ Something went wrong while searching. Please try again.")
        return

    track.requested_by_id = message.from_user.id
    track.requested_by_name = message.from_user.first_name or "Someone"

    await status.edit_text(f"✅ Found via {source_label} — preparing playback...")

    try:
        started, position = await player.play_or_enqueue(message.chat.id, track)
    except NoActiveVoiceChatError:
        await status.edit_text(
            "❌ **No Active Voice Chat Found**\n\nPlease start a Voice Chat in your group and try again."
        )
        return
    except OverflowError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error starting/queueing playback")
        await status.edit_text("⚠️ Playback failed unexpectedly. Please try again in a moment.")
        return

    await status.delete()

    if started:
        # The now-playing card is posted centrally by core.announcer for every
        # track start (covers /play, /skip, and natural auto-advance alike),
        # so nothing further is needed here.
        return
    else:
        queue_card_path = await generate_now_playing_card(
            title=track.title,
            artist=track.artist,
            duration_seconds=track.duration_seconds,
            elapsed_seconds=0,
            thumbnail_url=track.thumbnail_url,
            requested_by=track.requested_by_name,
            queue_position=position,
        )
        await message.reply_photo(
            photo=str(queue_card_path),
            caption=(
                f"➜ **Added To Queue #{position}**\n\n"
                f"**{track.title}**\n"
                f"⏱ {format_duration(track.duration_seconds)}\n"
                f"🙋 Requested by {track.requested_by_name}"
            ),
            quote=True,
)
    
