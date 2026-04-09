import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from reclip_client import (
    ReclipDownloadError,
    ReclipError,
    ReclipInfoError,
    ReclipServiceDown,
    get_info,
    poll_status,
    start_download,
)

logger = logging.getLogger(__name__)

DOWNLOADS_PATH = os.environ.get("DOWNLOADS_PATH", "/downloads")
URL_REGEX = re.compile(r"https?://[^\s<>\"']+")
STATE_TTL = 600  # 10 minutes

_state: dict[str, dict] = {}
_stats = {"downloads": 0, "errors": 0, "started": time.time()}
_user_prefs: dict[int, dict] = {}  # user_id -> {"quality": "best"|"720"|"480", "format": "video"|"audio"}

SUPPORTED_PLATFORMS = [
    "YouTube", "TikTok", "Instagram", "Twitter/X", "Reddit",
    "Facebook", "Vimeo", "Twitch", "Dailymotion", "SoundCloud",
    "Bandcamp", "Bilibili", "Pinterest", "Tumblr", "Threads",
    "LinkedIn", "Loom", "Streamable", "and 1000+ more via yt-dlp",
]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Hey! I'm ReClip Bot.\n\n"
        "Send me a video or audio link and I'll download it for you.\n\n"
        "Supported platforms: YouTube, TikTok, Instagram, Twitter, Reddit, "
        "and 1000+ more.\n\n"
        "Commands:\n"
        "/help - Help and commands\n"
        "/platforms - Supported platforms\n"
        "/settings - Your preferences\n"
        "/stats - Bot statistics\n"
        "/mp3 <link> - Download directly as MP3\n"
        "/mp4 <link> - Download best quality MP4\n"
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*How to use ReClip Bot:*\n\n"
        "1\\. Send a link \\(YouTube, TikTok, etc\\.\\)\n"
        "2\\. Pick a format \\(MP4 or MP3\\)\n"
        "3\\. Pick quality\n"
        "4\\. File delivered to the chat\\!\n\n"
        "*Shortcuts:*\n"
        "/mp3 \\<link\\> \\- Direct MP3 download\n"
        "/mp4 \\<link\\> \\- Best quality MP4\n"
        "/best \\<link\\> \\- Best available quality\n\n"
        "*Preferences:*\n"
        "/setquality \\<best/720/480\\> \\- Default quality\n"
        "/setformat \\<video/audio\\> \\- Default format\n"
        "/settings \\- View your preferences\n\n"
        "*Other:*\n"
        "/platforms \\- Supported sites\n"
        "/stats \\- Bot stats\n"
        "/cancel \\- Cancel \\(coming soon\\)\n\n"
        "You can also send multiple links in a single message\\!"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def cmd_platforms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Supported platforms:\n\n" + "\n".join(f"  {p}" for p in SUPPORTED_PLATFORMS)
    await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_s = int(time.time() - _stats["started"])
    hours, remainder = divmod(uptime_s, 3600)
    mins, secs = divmod(remainder, 60)

    downloads_dir = Path(DOWNLOADS_PATH)
    disk_mb = 0
    file_count = 0
    if downloads_dir.exists():
        for f in downloads_dir.iterdir():
            if f.is_file():
                disk_mb += f.stat().st_size / (1024 * 1024)
                file_count += 1

    text = (
        f"ReClip Bot Stats:\n\n"
        f"  Uptime: {hours}h {mins}m {secs}s\n"
        f"  Downloads: {_stats['downloads']}\n"
        f"  Errors: {_stats['errors']}\n"
        f"  Cached files: {file_count}\n"
        f"  Disk usage: {disk_mb:.1f} MB\n"
        f"  Active sessions: {len(_state)}\n"
    )
    await update.message.reply_text(text)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    prefs = _user_prefs.get(uid, {})
    quality = prefs.get("quality", "best")
    fmt = prefs.get("format", "video")
    text = (
        f"Your preferences:\n\n"
        f"  Default quality: {quality}\n"
        f"  Default format: {fmt}\n\n"
        f"Change:\n"
        f"  /setquality <best/720/480>\n"
        f"  /setformat <video/audio>\n"
    )
    await update.message.reply_text(text)


async def cmd_setquality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setquality <best/1080/720/480/360>")
        return
    q = context.args[0].lower()
    valid = ["best", "1080", "720", "480", "360"]
    if q not in valid:
        await update.message.reply_text(f"Invalid quality. Options: {', '.join(valid)}")
        return
    _user_prefs.setdefault(uid, {})["quality"] = q
    await update.message.reply_text(f"Default quality set to: {q}")


async def cmd_setformat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: /setformat <video/audio>")
        return
    f = context.args[0].lower()
    if f not in ("video", "audio"):
        await update.message.reply_text("Invalid format. Options: video, audio")
        return
    _user_prefs.setdefault(uid, {})["format"] = f
    await update.message.reply_text(f"Default format set to: {f}")


async def cmd_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct MP3 download without format picker."""
    text = update.message.text or ""
    urls = URL_REGEX.findall(text)
    if not urls:
        await update.message.reply_text("Usage: /mp3 <link>")
        return
    for url in urls:
        msg = await update.message.reply_text("Downloading MP3...")
        await _direct_download(update, msg, url, "audio", None)


async def cmd_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct best-quality MP4 download without format picker."""
    text = update.message.text or ""
    urls = URL_REGEX.findall(text)
    if not urls:
        await update.message.reply_text("Usage: /mp4 <link>")
        return
    for url in urls:
        msg = await update.message.reply_text("Downloading MP4 (best quality)...")
        await _direct_download(update, msg, url, "video", None)


async def cmd_best(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for /mp4."""
    await cmd_mp4(update, context)


async def _direct_download(update: Update, status_msg, url: str, fmt: str, format_id: str | None):
    """Download without the interactive picker flow."""
    try:
        info = await get_info(url)
    except ReclipServiceDown:
        await _edit_safe(status_msg, "Download service temporarily unavailable.")
        _stats["errors"] += 1
        return
    except ReclipError as e:
        await _edit_safe(status_msg, f"Error: {e}")
        _stats["errors"] += 1
        return

    title = info.get("title", "download")
    entry = {"url": url, "info": info, "user_id": update.effective_user.id}

    try:
        job_id = await start_download(url, fmt, format_id, title)
    except ReclipError as e:
        await _edit_safe(status_msg, f"Error: {e}")
        _stats["errors"] += 1
        return

    file_path = None
    for _ in range(150):
        await asyncio.sleep(2)
        try:
            status = await poll_status(job_id)
        except ReclipServiceDown:
            await _edit_safe(status_msg, "Download service unavailable.")
            _stats["errors"] += 1
            return
        except ReclipError:
            continue

        st = status.get("status")
        if st == "done":
            file_path = status.get("file_path") or status.get("filename")
            break
        elif st == "error":
            await _edit_safe(status_msg, f"Error: {status.get('error', 'Unknown error')}")
            _stats["errors"] += 1
            return
        else:
            progress = status.get("progress")
            if progress and isinstance(progress, dict) and progress.get("percent") is not None:
                text = f"Downloading... {progress['percent']}%"
            else:
                text = "Downloading..."
            try:
                await status_msg.edit_text(text)
            except Exception:
                pass

    if not file_path:
        await _edit_safe(status_msg, "Download timed out.")
        _stats["errors"] += 1
        return

    local_path = Path(DOWNLOADS_PATH) / Path(file_path).name
    if not local_path.exists():
        local_path = Path(file_path)
    if not local_path.exists():
        await _edit_safe(status_msg, "File not found after download.")
        _stats["errors"] += 1
        return

    for attempt in range(2):
        try:
            with open(local_path, "rb") as f:
                if fmt == "video" and local_path.suffix.lower() == ".mp4":
                    await update.message.chat.send_video(video=f, caption=title, supports_streaming=True)
                else:
                    await update.message.chat.send_document(document=f, caption=title)
            _stats["downloads"] += 1
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                await _edit_safe(status_msg, "Failed to upload file to Telegram.")
                _stats["errors"] += 1
                return

    try:
        await status_msg.edit_text(f"Sent: {title}")
    except Exception:
        pass
    try:
        local_path.unlink()
    except Exception:
        pass


def _state_key(chat_id: int, message_id: int, url_hash: str) -> str:
    return f"{chat_id}:{message_id}:{url_hash}"


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _evict_stale():
    now = time.time()
    expired = [k for k, v in _state.items() if now - v["created"] > STATE_TTL]
    for k in expired:
        del _state[k]


def _format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _build_format_buttons(message_id: int, url_hash: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("MP4", callback_data=f"fmt:{message_id}:{url_hash}:video"),
            InlineKeyboardButton("MP3", callback_data=f"fmt:{message_id}:{url_hash}:audio"),
        ]
    ])


def _build_quality_buttons(message_id: int, url_hash: str, formats: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for fmt in formats:
        label = fmt.get("label", fmt.get("id", "?"))
        buttons.append(
            InlineKeyboardButton(label, callback_data=f"qty:{message_id}:{url_hash}:{fmt['id']}")
        )
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("Best quality", callback_data=f"qty:{message_id}:{url_hash}:best")])
    return InlineKeyboardMarkup(rows)


async def url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _evict_stale()
    text = update.message.text or ""
    urls = URL_REGEX.findall(text)
    if not urls:
        return

    for url in urls:
        uhash = _url_hash(url)
        status_msg = await update.message.reply_text("Fetching info...")

        try:
            info = await get_info(url)
        except ReclipServiceDown:
            await status_msg.edit_text("Download service temporarily unavailable.")
            continue
        except ReclipInfoError as e:
            await status_msg.edit_text(f"Failed to fetch info: {e}")
            continue
        except ReclipError as e:
            await status_msg.edit_text(f"Error: {e}")
            continue

        title = info.get("title", "Unknown")
        extractor = info.get("extractor", "Unknown")
        duration = _format_duration(info.get("duration"))
        uploader = info.get("uploader", "")
        thumbnail = info.get("thumbnail")

        caption_lines = [
            f"*{_escape_md(title)}*",
            f"Platform: {_escape_md(extractor)}",
            f"Duration: {_escape_md(duration)}",
        ]
        if uploader:
            caption_lines.append(f"Uploader: {_escape_md(uploader)}")
        caption = "\n".join(caption_lines)

        key = _state_key(update.effective_chat.id, status_msg.message_id, uhash)
        _state[key] = {
            "url": url,
            "user_id": update.effective_user.id,
            "info": info,
            "message_id": status_msg.message_id,
            "created": time.time(),
        }

        keyboard = _build_format_buttons(status_msg.message_id, uhash)

        if thumbnail:
            try:
                await status_msg.delete()
                sent = await update.message.reply_photo(
                    photo=thumbnail,
                    caption=caption,
                    parse_mode="MarkdownV2",
                    reply_markup=keyboard,
                )
                _state[key]["message_id"] = sent.message_id
                old_key = key
                key = _state_key(update.effective_chat.id, sent.message_id, uhash)
                _state[key] = _state.pop(old_key)
            except Exception:
                logger.exception("Failed to send thumbnail, falling back to text")
                sent = await update.message.reply_text(
                    caption, parse_mode="MarkdownV2", reply_markup=keyboard
                )
                _state[key]["message_id"] = sent.message_id
                old_key = key
                key = _state_key(update.effective_chat.id, sent.message_id, uhash)
                _state[key] = _state.pop(old_key)
        else:
            await status_msg.edit_text(caption, parse_mode="MarkdownV2", reply_markup=keyboard)


def _escape_md(text: str) -> str:
    special = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _evict_stale()
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 4:
        return
    _, msg_id_str, uhash, fmt = parts
    msg_id = int(msg_id_str)

    key = _state_key(query.message.chat_id, msg_id, uhash)
    entry = _state.get(key)
    if not entry:
        key = _state_key(query.message.chat_id, query.message.message_id, uhash)
        entry = _state.get(key)
    if not entry:
        await query.edit_message_text("Session expired. Please send the link again.")
        return

    if fmt == "back":
        keyboard = _build_format_buttons(query.message.message_id, uhash)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        return

    if fmt == "audio":
        asyncio.create_task(
            download_and_send(query, entry, format="audio", format_id=None)
        )
    elif fmt == "video":
        formats = entry["info"].get("formats", [])
        if not formats:
            asyncio.create_task(
                download_and_send(query, entry, format="video", format_id=None)
            )
            return

        keyboard = _build_quality_buttons(query.message.message_id, uhash, formats[:6])
        await query.edit_message_reply_markup(reply_markup=keyboard)


async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _evict_stale()
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 4:
        return
    _, msg_id_str, uhash, format_id = parts
    msg_id = int(msg_id_str)

    key = _state_key(query.message.chat_id, msg_id, uhash)
    entry = _state.get(key)
    if not entry:
        key = _state_key(query.message.chat_id, query.message.message_id, uhash)
        entry = _state.get(key)
    if not entry:
        await query.edit_message_text("Session expired. Please send the link again.")
        return

    fid = None if format_id == "best" else format_id
    asyncio.create_task(
        download_and_send(query, entry, format="video", format_id=fid)
    )


async def download_and_send(query, entry: dict, format: str, format_id: str | None):
    chat_id = query.message.chat_id
    message = query.message
    url = entry["url"]
    title = entry["info"].get("title", "download")

    try:
        await message.edit_caption(caption="Starting download...") if message.photo else await message.edit_text("Starting download...")
    except Exception:
        pass

    try:
        job_id = await start_download(url, format, format_id, title)
    except ReclipServiceDown:
        await _edit_safe(message, "Download service temporarily unavailable.")
        _stats["errors"] += 1
        return
    except ReclipDownloadError as e:
        await _edit_safe(message, f"Download failed: {e}")
        _stats["errors"] += 1
        return
    except ReclipError as e:
        await _edit_safe(message, f"Error: {e}")
        _stats["errors"] += 1
        return

    file_path = None
    for _ in range(150):
        await asyncio.sleep(2)
        try:
            status = await poll_status(job_id)
        except ReclipServiceDown:
            await _edit_safe(message, "Download service temporarily unavailable.")
            _stats["errors"] += 1
            return
        except ReclipError:
            continue

        st = status.get("status")
        if st == "done":
            file_path = status.get("file_path") or status.get("filename")
            break
        elif st == "error":
            await _edit_safe(message, f"Error: {status.get('error', 'Unknown error')}")
            _stats["errors"] += 1
            return
        else:
            progress = status.get("progress")
            if progress and isinstance(progress, dict) and progress.get("percent") is not None:
                text = f"Downloading... {progress['percent']}%"
            else:
                text = "Downloading..."
            try:
                if message.photo:
                    await message.edit_caption(caption=text)
                else:
                    await message.edit_text(text)
            except Exception:
                pass

    if not file_path:
        await _edit_safe(message, "Download timed out.")
        _stats["errors"] += 1
        return

    local_path = Path(DOWNLOADS_PATH) / Path(file_path).name
    if not local_path.exists():
        local_path = Path(file_path)
    if not local_path.exists():
        await _edit_safe(message, "File not found after download.")
        _stats["errors"] += 1
        return

    for attempt in range(2):
        try:
            with open(local_path, "rb") as f:
                if format == "video" and local_path.suffix.lower() == ".mp4":
                    await query.message.chat.send_video(
                        video=f, caption=title, supports_streaming=True
                    )
                else:
                    await query.message.chat.send_document(document=f, caption=title)
            _stats["downloads"] += 1
            break
        except Exception:
            if attempt == 0:
                logger.warning("Upload failed, retrying once")
                await asyncio.sleep(1)
            else:
                logger.exception("Upload failed after retry")
                await _edit_safe(message, "Failed to upload file to Telegram.")
                _stats["errors"] += 1
                return

    try:
        if message.photo:
            await message.edit_caption(caption=f"Sent: {title}")
        else:
            await message.edit_text(f"Sent: {title}")
    except Exception:
        pass

    try:
        local_path.unlink()
    except Exception:
        logger.debug("Could not delete %s", local_path)


async def _edit_safe(message, text: str):
    try:
        if message.photo:
            await message.edit_caption(caption=text)
        else:
            await message.edit_text(text)
    except Exception:
        logger.debug("Failed to edit message with: %s", text)


def register_handlers(application):
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("platforms", cmd_platforms))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("settings", cmd_settings))
    application.add_handler(CommandHandler("setquality", cmd_setquality))
    application.add_handler(CommandHandler("setformat", cmd_setformat))
    application.add_handler(CommandHandler("mp3", cmd_mp3))
    application.add_handler(CommandHandler("mp4", cmd_mp4))
    application.add_handler(CommandHandler("best", cmd_best))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, url_handler))
    application.add_handler(CallbackQueryHandler(format_callback, pattern=r"^fmt:"))
    application.add_handler(CallbackQueryHandler(quality_callback, pattern=r"^qty:"))
