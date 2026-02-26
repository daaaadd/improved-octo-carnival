#!/usr/bin/env python3
"""
╔══════════════════════════════════════╗
║   🔥  S A V A G E  D O W N L O A D  ║
║         by @y_7_7_7_y               ║
╚══════════════════════════════════════╝
"""

import asyncio
import logging
import random
import re
import subprocess
import os
import hashlib
from pathlib import Path

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    Message,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import BadRequest
import yt_dlp

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOKEN        = "8562983961:AAG3BxIR24Ruqx0YsW_j36zlmvo3QFAmmsY"
AUTHOR       = "@y_7_7_7_y"
AUTHOR_CLEAN = "y_7_7_7_y"
DL_DIR       = Path("downloads")
DL_DIR.mkdir(exist_ok=True)

# Хранилище ссылок (url_id -> url)
URL_STORAGE: dict[str, str] = {}

logging.basicConfig(
    format="%(asctime)s │ %(levelname)s │ %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  FFMPEG CHECK

def check_ffmpeg() -> bool:
    for cmd in (["ffmpeg", "-version"], ["ffmpeg.exe", "-version"]):
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            log.info("✅ FFmpeg найден")
            return True
        except Exception:
            pass
    log.warning("⚠️ FFmpeg не найден — MP3 недоступен. Скачай: https://ffmpeg.org/download.html")
    return False


FFMPEG_OK = check_ffmpeg()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  CONSTANTS

PLATFORM_META = {
    "tiktok":    {"emoji": "🎵", "label": "TikTok",    "color": "🩷"},
    "youtube":   {"emoji": "▶️",  "label": "YouTube",   "color": "❤️"},
    "instagram": {"emoji": "📸", "label": "Instagram", "color": "💜"},
    "unknown":   {"emoji": "🔗", "label": "Ссылка",    "color": "🤍"},
}

SURPRISES = [
    "💀 Тихо скачал — никто не узнал.",
    "⚡ Быстро, грязно, эффективно.",
    "🌚 Скачал. Посмотрел. Никому не сказал.",
    "🔥 Го ещё одно!",
    "🎲 Удача на твоей стороне.",
    "🦁 Лев не спрашивает разрешения.",
    "🕶️ Смотришь со стилем.",
]

LOADING_STAGES = [
    ("⣾", "░░░░░░░░░░",  "0%  "),
    ("⣽", "██░░░░░░░░", "20% "),
    ("⣻", "████░░░░░░", "40% "),
    ("⢿", "██████░░░░", "60% "),
    ("⣯", "████████░░", "80% "),
    ("✅", "██████████", "100%"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  HELPERS

URL_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com"
    r"|youtube\.com|youtu\.be"
    r"|instagram\.com|instagr\.am)"
    r"[^\s]*",
    re.IGNORECASE,
)


def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok" in u:                       return "tiktok"
    if "youtube" in u or "youtu.be" in u:   return "youtube"
    if "instagram" in u or "instagr" in u:  return "instagram"
    return "unknown"


def get_url_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def is_text_message(msg: Message) -> bool:
    """Проверяем — есть ли в сообщении текст (не медиа)."""
    return bool(msg.text or msg.caption) and not (
        msg.audio or msg.video or msg.voice or msg.document or msg.photo
    )


async def safe_edit_text(msg: Message, text: str, **kwargs) -> Message:
    """
    Редактируем текст если можем, иначе отправляем новое сообщение.
    Это фикс ошибки 'There is no text in the message to edit'
    которая возникает при нажатии кнопки на медиа-сообщении (аудио/видео).
    """
    if is_text_message(msg):
        try:
            return await msg.edit_text(text, **kwargs)
        except BadRequest as e:
            if "There is no text" in str(e) or "Message can't be edited" in str(e):
                pass
            else:
                raise
    # Отправляем как новое сообщение в тот же чат
    return await msg.reply_text(text, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  KEYBOARDS

def kb_main():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 TikTok",   callback_data="info_tiktok"),
            InlineKeyboardButton("▶️ YouTube",   callback_data="info_youtube"),
            InlineKeyboardButton("📸 Insta",     callback_data="info_insta"),
        ],
        [
            InlineKeyboardButton("🎲 Сюрприз",  callback_data="surprise"),
            InlineKeyboardButton("👤 Автор",    callback_data="author"),
            InlineKeyboardButton("❓ Помощь",   callback_data="help"),
        ],
    ])


def kb_back():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
        InlineKeyboardButton("🏠 Меню",  callback_data="back_main"),
    ]])


def kb_download(url: str, platform: str):
    url_id = get_url_id(url)
    URL_STORAGE[url_id] = url
    meta = PLATFORM_META.get(platform, PLATFORM_META["unknown"])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬  ВИДЕО", callback_data=f"dl_video|{url_id}"),
            InlineKeyboardButton("🎵  АУДИО", callback_data=f"dl_audio|{url_id}"),
        ],
        [
            InlineKeyboardButton(f"{meta['color']} {meta['label']}", callback_data="noop"),
            InlineKeyboardButton("🏠 Меню", callback_data="back_main"),
        ],
    ])


def kb_after_download(url_id: str, done_mode: str):
    """
    Кнопка второго формата после скачивания.
    Эта клавиатура вешается на медиа-сообщение — 
    поэтому при нажатии нельзя делать edit_text, только reply.
    """
    other_mode  = "audio" if done_mode == "video" else "video"
    other_label = "🎵  АУДИО тоже" if other_mode == "audio" else "🎬  ВИДЕО тоже"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(other_label, callback_data=f"dl_{other_mode}|{url_id}")],
        [
            InlineKeyboardButton("🔁 Ещё ссылку", callback_data="back_main"),
            InlineKeyboardButton("🏠 Меню",        callback_data="back_main"),
        ],
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ANIMATION

async def animate_loading(msg: Message, mode: str):
    title = "🎬 Качаю видос..." if mode == "video" else "🎵 Рву аудио на части..."
    for spin, bar, pct in LOADING_STAGES:
        try:
            await msg.edit_text(
                f"{title}\n\n`{bar}` {pct}\n{spin}  обрабатываю...",
                parse_mode="Markdown",
            )
            await asyncio.sleep(0.45)
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  DOWNLOAD

async def download_media(url: str, mode: str):
    out_tmpl = str(DL_DIR / "%(id)s.%(ext)s")

    if mode == "audio":
        if FFMPEG_OK:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": out_tmpl,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
                "no_warnings": True,
            }
        else:
            opts = {
                "format": "bestaudio[ext=m4a]/bestaudio",
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
            }
    else:
        opts = {
            "format": (
                "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]"
                "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/best[ext=mp4]/best"
            ),
            "outtmpl": out_tmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

    loop = asyncio.get_event_loop()

    def _dl():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info     = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                if mode == "audio" and FFMPEG_OK:
                    mp3 = Path(filename).with_suffix(".mp3")
                    if mp3.exists():
                        return mp3

                p = Path(filename)
                if p.exists():
                    return p

                # Fallback — берём последний скачанный файл
                files = sorted(DL_DIR.glob("*"), key=lambda f: f.stat().st_mtime)
                return files[-1] if files else None
        except Exception as e:
            log.error("Download error: %s", e)
            return None

    return await loop.run_in_executor(None, _dl)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  COMMANDS

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "бро"
    await update.message.reply_text(
        "╔══════════════════════╗\n"
        "║  🔥  SAVAGE DOWNLOAD  ║\n"
        "╚══════════════════════╝\n\n"
        f"Слышь, *{name}* 👋\n"
        "Кидай ссылку — я решу вопрос\n"
        "TikTok / YouTube / Insta — без разницы\n\n"
        f"👤 `{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )


async def cmd_surprise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    opts = [
        ("🎰", "Слот дня",      "🍒 🍒 🍒 — ДЖЕКПОТ!\nСкачай что-нибудь — заслужил."),
        ("🎱", "8-ball говорит", "Все знаки указывают — *да*."),
        ("🔮", "Пророчество",   "Сегодня скачаешь что-то эпичное."),
        ("⚡", "Факт",          "yt-dlp скачал больше видео, чем ты посмотрел за всю жизнь."),
        ("🌌", "Космос",        "Где-то во вселенной кто-то тоже качает TikTok прямо сейчас."),
        ("🎭", "Театр абсурда", "Ты нажал на сюрприз. Это и был сюрприз. Конец."),
        ("🦁", "Мудрость",      "Лев не спрашивает разрешения. Кидай ссылку."),
    ]
    icon, title, text = random.choice(opts)
    await update.message.reply_text(
        f"{icon} *{title}*\n\n{text}\n\n`{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ffmpeg_status = "✅ Есть (MP3 работает)" if FFMPEG_OK else "❌ Нет (установи ffmpeg для MP3)"
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "┌─ Как использовать\n"
        "│  Скинь ссылку в чат\n"
        "│  Выбери: ВИДЕО или АУДИО\n"
        "└──────────────────────\n\n"
        "📌 *Платформы:*\n"
        "🎵  TikTok\n"
        "▶️   YouTube / Shorts\n"
        "📸  Instagram Reels\n\n"
        "📥 *Форматы:*\n"
        "🎬  ВИДЕО → MP4\n"
        "🎵  АУДИО → MP3 (192 kbps)\n\n"
        f"FFmpeg: {ffmpeg_status}\n\n"
        f"`{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  MESSAGE HANDLER

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text  = update.message.text or ""
    match = URL_RE.search(text)

    if not match:
        await update.message.reply_text(
            "🤔 *Не вижу ссылки...*\n\n"
            "Скинь ссылку на видео:\n"
            "TikTok / YouTube / Instagram 👇",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    platform = detect_platform(url)
    meta     = PLATFORM_META.get(platform, PLATFORM_META["unknown"])

    await update.message.reply_text(
        f"{meta['color']} *{meta['label']}* — поймал!\n\nЧто качаем? 👇",
        parse_mode="Markdown",
        reply_markup=kb_download(url, platform),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  CALLBACK HANDLER

PLATFORM_INFO_TEXTS = {
    "info_tiktok": (
        "🎵 *TikTok*\n\n"
        "Все форматы ссылок:\n"
        "• tiktok.com/@user/video/...\n"
        "• vm.tiktok.com/...\n"
        "• vt.tiktok.com/...\n\n"
        "✅ Без авторизации"
    ),
    "info_youtube": (
        "▶️ *YouTube*\n\n"
        "Поддерживается:\n"
        "• youtube.com/watch?v=...\n"
        "• youtu.be/...\n"
        "• YouTube Shorts\n\n"
        "⚠️ Видео >50 МБ Telegram не примет"
    ),
    "info_insta": (
        "📸 *Instagram*\n\n"
        "Работает с:\n"
        "• Reels (instagram.com/reel/...)\n"
        "• Посты с видео\n\n"
        "⚠️ Сторис требуют авторизации"
    ),
}


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    msg   = query.message   # может быть текстовым ИЛИ медиа-сообщением

    # ── МЕНЮ ──────────────────────────────────────────────────────
    if data in ("back_main", "menu"):
        name = update.effective_user.first_name or "бро"
        text = (
            "╔══════════════════════╗\n"
            "║  🔥  SAVAGE DOWNLOAD  ║\n"
            "╚══════════════════════╝\n\n"
            f"Слышь, *{name}* 👋\n"
            "Кидай ссылку — я решу вопрос\n"
            "TikTok / YouTube / Insta — без разницы"
        )
        await safe_edit_text(msg, text, parse_mode="Markdown", reply_markup=kb_main())
        return

    if data == "noop":
        return

    # ── ИНФО О ПЛАТФОРМАХ ─────────────────────────────────────────
    if data in PLATFORM_INFO_TEXTS:
        await safe_edit_text(
            msg,
            PLATFORM_INFO_TEXTS[data],
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── СЮРПРИЗ ───────────────────────────────────────────────────
    if data == "surprise":
        opts = [
            "🎰  🍒 🍒 🍒 — ДЖЕКПОТ!",
            "🎱  Все знаки говорят — *кидай ссылку*.",
            "🔮  Сегодня скачаешь что-то эпичное.",
            "⚡  yt-dlp быстрее твоего интернета.",
            "🌚  Тихий час. Качай тихо.",
            "🎭  Ты нажал сюрприз. Сюрприз — это я. Привет.",
            "🦁  Лев не спрашивает разрешения. Ты тоже.",
        ]
        await safe_edit_text(
            msg,
            f"🎲 *СЮРПРИЗ*\n\n{random.choice(opts)}\n\n`{AUTHOR}`",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── АВТОР ─────────────────────────────────────────────────────
    if data == "author":
        await safe_edit_text(
            msg,
            f"👤 *Автор*\n\n`{AUTHOR}`\nt.me/{AUTHOR_CLEAN}\n\nСделал этот бот чтобы облегчить жизнь 🔥",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── ПОМОЩЬ ────────────────────────────────────────────────────
    if data == "help":
        ffmpeg_status = "✅" if FFMPEG_OK else "❌ (установи ffmpeg)"
        await safe_edit_text(
            msg,
            f"❓ *Помощь*\n\nСкинь ссылку → выбери формат → готово\n\n"
            f"🎵 TikTok │ ▶️ YouTube │ 📸 Insta\n"
            f"🎬 ВИДЕО (MP4) │ 🎵 АУДИО (MP3)\n\n"
            f"FFmpeg: {ffmpeg_status}\n\n`{AUTHOR}`",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── СКАЧИВАНИЕ ────────────────────────────────────────────────
    if data.startswith(("dl_video|", "dl_audio|")):
        mode, url_id = data.split("|", 1)
        mode = mode[3:]   # "video" или "audio"

        url = URL_STORAGE.get(url_id)
        if not url:
            await safe_edit_text(
                msg,
                "❌ *Ссылка устарела*\n\nОтправь ссылку заново 👇",
                parse_mode="Markdown",
                reply_markup=kb_back(),
            )
            return

        platform = detect_platform(url)
        meta     = PLATFORM_META.get(platform, PLATFORM_META["unknown"])

        # ── Статусное сообщение — ВСЕГДА новое (reply),
        #    потому что query.message может быть медиа-файлом
        title_anim = "🎬 Качаю видос..." if mode == "video" else "🎵 Рву аудио на части..."
        status = await msg.reply_text(
            f"{title_anim}\n\n`░░░░░░░░░░` 0%\n⣾  обрабатываю...",
            parse_mode="Markdown",
        )

        # ── Анимация + скачивание параллельно
        anim_task = asyncio.create_task(animate_loading(status, mode))
        file_path = await download_media(url, mode)
        anim_task.cancel()

        # ── Ошибка скачивания
        if not file_path or not file_path.exists():
            err = "❌ *Не смог скачать*\n\n"
            if "tiktok" in url:
                err += "TikTok может банить IP\n👉 Попробуй включить VPN"
            else:
                err += "Причины:\n• Приватный аккаунт\n• Видео удалено\n• Ссылка устарела"
            await status.edit_text(err, parse_mode="Markdown", reply_markup=kb_back())
            return

        # ── Финал анимации
        await status.edit_text(
            f"{title_anim}\n\n`██████████` 100%\n✅  отправляю...",
            parse_mode="Markdown",
        )

        try:
            chat_id  = msg.chat_id
            mb       = file_path.stat().st_size / 1024 / 1024
            surprise = random.choice(SURPRISES)
            after_kb = kb_after_download(url_id, mode)

            if file_path.stat().st_size > 50 * 1024 * 1024:
                await status.edit_text(
                    "⚠️ *Файл слишком большой* (>50 МБ)\n\nTelegram не принимает такие файлы.\nПопробуй другое видео.",
                    parse_mode="Markdown",
                    reply_markup=kb_back(),
                )
                file_path.unlink(missing_ok=True)
                return

            caption = (
                f"{'🎵 Аудио' if mode == 'audio' else '🎬 Видео'} готово!\n"
                f"┌──────────────────\n"
                f"│ 📦 {mb:.1f} МБ  │  {'MP3 192kbps' if mode == 'audio' else 'MP4'}\n"
                f"│ {meta['emoji']} {meta['label']}\n"
                f"└──────────────────\n\n"
                f"{surprise}\n\n"
                f"`{AUTHOR}`"
            )

            ext = file_path.suffix.lower()
            if mode == "audio" or ext in (".mp3", ".m4a", ".ogg"):
                with open(file_path, "rb") as f:
                    await ctx.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=after_kb,
                    )
            else:
                with open(file_path, "rb") as f:
                    await ctx.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=caption,
                        parse_mode="Markdown",
                        supports_streaming=True,
                        reply_markup=after_kb,
                    )

            # Удаляем статусное сообщение
            await status.delete()

        except Exception as e:
            log.error("Send error: %s", e)
            await status.edit_text(
                f"❌ Ошибка при отправке:\n`{str(e)[:120]}`",
                parse_mode="Markdown",
                reply_markup=kb_back(),
            )
        finally:
            if file_path and file_path.exists():
                file_path.unlink(missing_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  MAIN

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",    "🚀 Запуск"),
        BotCommand("surprise", "🎲 Сюрприз"),
        BotCommand("help",     "❓ Помощь"),
    ])
    log.info("✅ Бот запущен!  │  %s", AUTHOR)


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("surprise", cmd_surprise))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("🤖 Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

