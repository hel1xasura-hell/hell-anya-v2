"""
utils/thumbnail.py
===================
Generates the "now playing" card: album art with a blurred background,
gradient overlay, rounded corners and purple/black premium typography.

Font handling
-------------
Ships no proprietary font files (to avoid licensing issues in a
distributable repo). On first run it looks for ``assets/fonts/*.ttf``; if
none are present it falls back to Pillow's built-in default font so the
bot still produces a usable (if less polished) card out of the box. Drop
any ``.ttf``/``.otf`` font into ``assets/fonts/`` — e.g. Poppins or
Montserrat — to get the full premium look shown in the README.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from config import FONTS_DIR, config
from utils.formatters import format_duration, progress_bar, truncate

logger = logging.getLogger(__name__)

CARD_SIZE = (1280, 720)
ACCENT_PURPLE = (138, 43, 226)
ACCENT_PURPLE_DARK = (52, 15, 92)
TEXT_WHITE = (245, 245, 250)
TEXT_MUTED = (200, 190, 215)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = sorted(FONTS_DIR.glob("*Bold*")) if bold else sorted(FONTS_DIR.glob("*.ttf")) + sorted(FONTS_DIR.glob("*.otf"))
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


async def _download_image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                data = await response.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:  # noqa: BLE001
        logger.warning("Failed to download artwork from %s", url, exc_info=True)
        return None


def _build_blurred_background(album_art: Image.Image | None) -> Image.Image:
    canvas = Image.new("RGBA", CARD_SIZE, ACCENT_PURPLE_DARK + (255,))
    if album_art is not None:
        background = ImageOps.fit(album_art.convert("RGB"), CARD_SIZE, Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(28))
        canvas = Image.alpha_composite(canvas, background.convert("RGBA"))

    gradient = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for x in range(CARD_SIZE[0]):
        ratio = x / CARD_SIZE[0]
        alpha = int(235 - 120 * ratio)
        r = int(ACCENT_PURPLE_DARK[0] * (1 - ratio) + 5 * ratio)
        g = int(ACCENT_PURPLE_DARK[1] * (1 - ratio) + 5 * ratio)
        b = int(ACCENT_PURPLE_DARK[2] * (1 - ratio) + 10 * ratio)
        gradient_draw.line([(x, 0), (x, CARD_SIZE[1])], fill=(r, g, b, alpha))

    return Image.alpha_composite(canvas, gradient)


async def generate_now_playing_card(
    *,
    title: str,
    artist: str,
    duration_seconds: int,
    elapsed_seconds: int,
    thumbnail_url: str,
    requested_by: str,
    queue_position: int,
) -> Path:
    """Render the now-playing card and return the path to the PNG file."""

    album_art = await _download_image(thumbnail_url)
    card = _build_blurred_background(album_art)
    draw = ImageDraw.Draw(card)

    art_size = 420
    art_pos = (70, 150)
    if album_art is not None:
        art = ImageOps.fit(album_art.convert("RGB"), (art_size, art_size), Image.LANCZOS).convert("RGBA")
    else:
        art = Image.new("RGBA", (art_size, art_size), ACCENT_PURPLE + (255,))
    mask = _rounded_mask((art_size, art_size), radius=32)

    shadow = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (art_pos[0] + 12, art_pos[1] + 16, art_pos[0] + art_size + 12, art_pos[1] + art_size + 16),
        radius=32,
        fill=(0, 0, 0, 140),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    card = Image.alpha_composite(card, shadow)
    card.paste(art, art_pos, mask)
    draw = ImageDraw.Draw(card)

    text_x = art_pos[0] + art_size + 60
    font_title = _load_font(52, bold=True)
    font_artist = _load_font(34)
    font_meta = _load_font(26)
    font_brand = _load_font(30, bold=True)

    draw.text((text_x, 150), truncate(title, 28), font=font_title, fill=TEXT_WHITE)
    draw.text((text_x, 220), truncate(artist, 34), font=font_artist, fill=TEXT_MUTED)

    bar_y = 320
    bar_text = f"{format_duration(elapsed_seconds)}  {progress_bar(elapsed_seconds, duration_seconds, length=24)}  {format_duration(duration_seconds)}"
    draw.text((text_x, bar_y), bar_text, font=font_meta, fill=TEXT_WHITE)

    draw.text((text_x, bar_y + 60), f"Requested by  {truncate(requested_by, 24)}", font=font_meta, fill=TEXT_MUTED)
    if queue_position:
        draw.text((text_x, bar_y + 100), f"Queue position  #{queue_position}", font=font_meta, fill=TEXT_MUTED)

    draw.rounded_rectangle((70, 60, 340, 116), radius=20, fill=ACCENT_PURPLE + (230,))
    draw.text((92, 72), config.bot_name.upper(), font=font_brand, fill=TEXT_WHITE)

    from config import CACHE_DIR

    output_path = CACHE_DIR / "now_playing.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path
