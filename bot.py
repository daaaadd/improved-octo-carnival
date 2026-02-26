#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════╗
║          🔥  S A V A G E  D O W N L O A D E R           ║
║                    by @y_7_7_7_y                         ║
╠══════════════════════════════════════════════════════════╣
║  ✅ TikTok / YouTube / Instagram                         ║
║  ✅ Видео (MP4) + Аудио (MP3 или M4A без FFmpeg)         ║
║  ✅ Антибан: прокси, UA-ротация, задержки, ретраи        ║
║  ✅ Работает на дешёвом хостинге без FFmpeg              ║
║  ✅ Не падает при нажатии кнопок на медиа-сообщениях     ║
╚══════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════
#  ИМПОРТЫ
# ══════════════════════════════════════════════════════════

import asyncio
import hashlib
import logging
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yt_dlp
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.error import BadRequest, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ══════════════════════════════════════════════════════════
#  ⚙️  КОНФИГ — ВСЁ НАСТРАИВАЕТСЯ ЗДЕСЬ
# ══════════════════════════════════════════════════════════

# ── Основное ──────────────────────────────────────────────
TOKEN        = "8562983961:AAG3BxIR24Ruqx0YsW_j36zlmvo3QFAmmsY"
AUTHOR       = "@y_7_7_7_y"
AUTHOR_CLEAN = "y_7_7_7_y"
DL_DIR       = Path("downloads")   # папка для временных файлов
DL_DIR.mkdir(exist_ok=True)

# ── Прокси ────────────────────────────────────────────────
# None = прокси выключен
# Форматы:
#   HTTP:   "http://user:pass@1.2.3.4:8080"
#   SOCKS5: "socks5://user:pass@1.2.3.4:1080"
#   Без авторизации: "socks5://1.2.3.4:1080"
PROXY: Optional[str] = None

# ── Антибан-задержки (секунды) ────────────────────────────
DELAY_MIN = 1.5   # минимум перед скачиванием
DELAY_MAX = 4.5   # максимум перед скачиванием

# ── Авто-ретраи ───────────────────────────────────────────
RETRY_COUNT   = 4    # сколько попыток
RETRY_DELAY   = 5    # секунд между попытками

# ── Ограничение размера файла (Telegram принимает ≤50 МБ) ─
MAX_FILE_MB   = 49

# ══════════════════════════════════════════════════════════
#  ЛОГИРОВАНИЕ
# ══════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s │ %(levelname)-8s │ %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  ПРОВЕРКА FFMPEG
# ══════════════════════════════════════════════════════════

def check_ffmpeg() -> bool:
    """
    Проверяем наличие FFmpeg в системе.
    Если его нет — аудио будет в M4A, видео без склейки форматов.
    Это НЕ критично — бот работает в любом случае.
    """
    for cmd in (["ffmpeg", "-version"], ["ffmpeg.exe", "-version"]):
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=5
            )
            if result.returncode == 0:
                log.info("✅ FFmpeg найден — MP3 доступен")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    log.warning("⚠️  FFmpeg НЕ найден — аудио будет в M4A (MP3 недоступен)")
    log.warning("    Установи FFmpeg: https://ffmpeg.org/download.html")
    return False


FFMPEG_OK = check_ffmpeg()


# ══════════════════════════════════════════════════════════
#  ПУЛЫ USER-AGENT'ОВ
# ══════════════════════════════════════════════════════════
# Реальные User-Agent'ы — новый при каждом запросе.
# Это главный способ обмануть антибот-защиту платформ.

# Десктопные браузеры (для YouTube и Instagram)
UA_DESKTOP = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome Linux (хостинги)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    # Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
]

# Мобильные (для TikTok — работает лучше)
UA_MOBILE = [
    # Chrome Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.178 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Redmi Note 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    # Safari iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
]

# TikTok-приложение (максимальный шанс обойти блокировку)
UA_TIKTOK_APP = [
    "TikTok 26.2.0 rv:262018 (iPhone; iOS 16.7.5; en_US) Cronet",
    "TikTok 27.0.3 rv:270203 (Android; U; Android 13; en_US) Cronet",
    "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 12; en_US; Pixel 6; Build/SP2A.220305.012; Cronet/58.0.2991.0)",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) TikTok/26.2.0 Mobile/15E148 Safari/604.1",
]


def pick_ua(platform: str = "unknown") -> str:
    """Выбираем случайный User-Agent под платформу."""
    if platform == "tiktok":
        # Для TikTok — смешиваем мобильные и ТТ-приложение
        pool = UA_MOBILE + UA_TIKTOK_APP
    elif platform == "instagram":
        pool = UA_MOBILE + UA_DESKTOP
    else:
        pool = UA_DESKTOP + UA_MOBILE
    return random.choice(pool)


# ══════════════════════════════════════════════════════════
#  ХРАНИЛИЩЕ ССЫЛОК
# ══════════════════════════════════════════════════════════
# Telegram ограничивает callback_data до 64 байт.
# Поэтому храним URL в словаре, а в кнопки пишем короткий md5-ключ.

URL_STORE: dict[str, str] = {}   # {url_id: url}


def store_url(url: str) -> str:
    """Сохраняем URL и возвращаем его короткий ID."""
    uid = hashlib.md5(url.encode()).hexdigest()[:10]
    URL_STORE[uid] = url
    return uid


def get_url(uid: str) -> Optional[str]:
    """Достаём URL по ID."""
    return URL_STORE.get(uid)


# ══════════════════════════════════════════════════════════
#  ОПРЕДЕЛЕНИЕ ПЛАТФОРМЫ
# ══════════════════════════════════════════════════════════

URL_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com"
    r"|youtube\.com|youtu\.be"
    r"|instagram\.com|instagr\.am)"
    r"[^\s]*",
    re.IGNORECASE,
)

PLATFORM_META = {
    "tiktok":    {"emoji": "🎵", "label": "TikTok",    "color": "🩷"},
    "youtube":   {"emoji": "▶️",  "label": "YouTube",   "color": "❤️"},
    "instagram": {"emoji": "📸", "label": "Instagram", "color": "💜"},
    "unknown":   {"emoji": "🔗", "label": "Ссылка",    "color": "🤍"},
}


def detect_platform(url: str) -> str:
    u = url.lower()
    if "tiktok" in u:                       return "tiktok"
    if "youtube" in u or "youtu.be" in u:   return "youtube"
    if "instagram" in u or "instagr" in u:  return "instagram"
    return "unknown"


# ══════════════════════════════════════════════════════════
#  ПОСТРОЕНИЕ ОПЦИЙ YT-DLP (АНТИБАН)
# ══════════════════════════════════════════════════════════

def build_opts(url: str, mode: str) -> dict:
    """
    Строим полные опции yt-dlp с антибан-защитой.

    mode = "video" | "audio"

    Что делаем:
    1. Случайный User-Agent под платформу
    2. Прокси если настроен
    3. Специальные HTTP-заголовки (как у браузера)
    4. TikTok-специфичные заголовки
    5. Гео-обход (US)
    6. Формат без FFmpeg если нужно
    """
    platform = detect_platform(url)
    ua       = pick_ua(platform)
    out_tmpl = str(DL_DIR / "%(id)s.%(ext)s")

    # ── Базовые антибан-параметры ──────────────────────────
    opts = {
        "outtmpl":            out_tmpl,
        "quiet":              True,
        "no_warnings":        True,
        "nocheckcertificate": True,      # SSL на хостингах часто ломается
        "geo_bypass":         True,      # обход гео-ограничений
        "geo_bypass_country": "US",      # притворяемся из США
        "socket_timeout":     30,        # таймаут соединения (сек)
        "retries":            2,         # встроенные yt-dlp ретраи
        "fragment_retries":   2,
        "user_agent":         ua,
        # HTTP заголовки — максимально похожи на браузер
        "http_headers": {
            "User-Agent":               ua,
            "Accept":                   "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language":          "en-US,en;q=0.9,ru;q=0.8",
            "Accept-Encoding":          "gzip, deflate, br",
            "DNT":                      "1",
            "Connection":               "keep-alive",
            "Upgrade-Insecure-Requests":"1",
            "Sec-Fetch-Dest":           "document",
            "Sec-Fetch-Mode":           "navigate",
            "Sec-Fetch-Site":           "none",
        },
    }

    # ── Прокси ────────────────────────────────────────────
    if PROXY:
        opts["proxy"] = PROXY
        proxy_display = PROXY.split("@")[-1] if "@" in PROXY else PROXY
        log.info("🔀 Прокси: %s", proxy_display)

    # ── TikTok — специальные заголовки ────────────────────
    if platform == "tiktok":
        opts["http_headers"].update({
            "Referer":             "https://www.tiktok.com/",
            "Origin":              "https://www.tiktok.com",
            "sec-ch-ua":           '"Chromium";v="122","Not(A:Brand";v="24","Google Chrome";v="122"',
            "sec-ch-ua-mobile":    "?1",                  # притворяемся мобильным
            "sec-ch-ua-platform":  '"Android"',
            "Sec-Fetch-Site":      "same-origin",
        })
        # Пробуем альтернативный API эндпоинт TikTok
        opts["extractor_args"] = {
            "tiktok": {
                "webpage_download": ["true"],
            }
        }

    # ── Instagram ─────────────────────────────────────────
    elif platform == "instagram":
        opts["http_headers"].update({
            "Referer": "https://www.instagram.com/",
            "Origin":  "https://www.instagram.com",
        })

    # ── YouTube ───────────────────────────────────────────
    elif platform == "youtube":
        opts["http_headers"].update({
            "Referer": "https://www.youtube.com/",
        })

    # ── ФОРМАТ: АУДИО ─────────────────────────────────────
    if mode == "audio":
        if FFMPEG_OK:
            # FFmpeg есть → конвертируем в MP3
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "192",
            }]
        else:
            # FFmpeg нет → качаем лучшее аудио как есть (обычно M4A или WebM)
            # Это решение проблемы "merging of multiple formats"
            opts["format"] = (
                "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio[ext=webm]"
                "/bestaudio/best[ext=m4a]/best"
            )

    # ── ФОРМАТ: ВИДЕО ─────────────────────────────────────
    else:
        if FFMPEG_OK:
            # FFmpeg есть → лучшее видео + аудио, склеиваем в MP4
            opts["format"] = (
                "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]"
                "/bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[filesize<45M]+bestaudio"
                "/best[ext=mp4]/best"
            )
            opts["merge_output_format"] = "mp4"
        else:
            # FFmpeg нет → ищем уже готовый файл MP4 без склейки
            # Это решение ошибки "merging of multiple formats is not supported"
            opts["format"] = (
                "best[ext=mp4][filesize<45M]"
                "/best[ext=mp4]"
                "/best[filesize<45M]"
                "/best"
            )

    return opts


# ══════════════════════════════════════════════════════════
#  СКАЧИВАНИЕ С РЕТРАЯМИ И АНТИБАНОМ
# ══════════════════════════════════════════════════════════

async def download_media(url: str, mode: str) -> Optional[Path]:
    """
    Главная функция скачивания.

    Алгоритм:
    1. Случайная задержка (антибан)
    2. Попытка скачать
    3. При неудаче — пауза и новая попытка с другим UA
    4. Возвращает Path к файлу или None если все попытки провалились
    """

    # ── Случайная задержка перед стартом ──────────────────
    if DELAY_MAX > 0:
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        log.info("⏳ Антибан-задержка: %.1f сек", delay)
        await asyncio.sleep(delay)

    loop = asyncio.get_event_loop()

    for attempt in range(1, RETRY_COUNT + 1):
        opts = build_opts(url, mode)
        ua_short = opts["user_agent"][:55].rstrip() + "…"
        log.info("📥 Попытка %d/%d | %s | UA: %s",
                 attempt, RETRY_COUNT, mode.upper(), ua_short)

        def _blocking_download() -> Optional[Path]:
            """Синхронная часть — запускается в отдельном потоке."""
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info     = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)

                    # Проверяем варианты имени файла ──────────────
                    candidates = [
                        Path(filename),
                        Path(filename).with_suffix(".mp4"),
                        Path(filename).with_suffix(".mp3"),
                        Path(filename).with_suffix(".m4a"),
                        Path(filename).with_suffix(".webm"),
                    ]
                    for cand in candidates:
                        if cand.exists():
                            log.info("✅ Файл найден: %s (%.1f МБ)",
                                     cand.name, cand.stat().st_size / 1024 / 1024)
                            return cand

                    # Fallback — берём самый свежий файл в папке
                    all_files = [f for f in DL_DIR.iterdir() if f.is_file()]
                    if all_files:
                        newest = max(all_files, key=lambda f: f.stat().st_mtime)
                        log.info("✅ Fallback файл: %s", newest.name)
                        return newest

                    log.error("❌ Файл не найден после скачивания")
                    return None

            except yt_dlp.utils.DownloadError as e:
                err = str(e).lower()
                # Логируем понятные сообщения для каждой ошибки
                if "blocked" in err or "ip" in err:
                    log.warning("🚫 Попытка %d: IP заблокирован платформой", attempt)
                elif "private" in err:
                    log.warning("🔒 Попытка %d: приватный аккаунт", attempt)
                elif "unavailable" in err or "not found" in err:
                    log.warning("❓ Попытка %d: видео недоступно", attempt)
                elif "merge" in err or "ffmpeg" in err:
                    log.warning("🔧 Попытка %d: проблема с FFmpeg — меняем формат", attempt)
                else:
                    log.warning("⚠️  Попытка %d: %s", attempt, str(e)[:120])
                return None

            except Exception as e:
                log.error("💥 Попытка %d: неожиданная ошибка: %s", attempt, e)
                return None

        # Запускаем в executor чтобы не блокировать event loop
        result = await loop.run_in_executor(None, _blocking_download)

        if result and result.exists():
            return result

        # Не вышло — ждём перед следующей попыткой
        if attempt < RETRY_COUNT:
            # Случайная пауза + увеличивающаяся задержка (exponential backoff)
            wait = RETRY_DELAY + random.uniform(1, 3) * attempt
            log.info("🔄 Следующая попытка через %.1f сек...", wait)
            await asyncio.sleep(wait)

    log.error("💀 Все %d попытки провалились для: %s", RETRY_COUNT, url)
    return None


# ══════════════════════════════════════════════════════════
#  ФИКС: РЕДАКТИРОВАНИЕ МЕДИА-СООБЩЕНИЙ
# ══════════════════════════════════════════════════════════

def is_editable(msg: Message) -> bool:
    """
    Проверяем, можно ли редактировать сообщение.
    Медиа-сообщения (аудио, видео) нельзя редактировать через edit_text.
    Это была главная причина ошибки 'There is no text in the message to edit'.
    """
    has_text = bool(msg.text)
    is_media = bool(
        msg.audio or msg.video or msg.voice or
        msg.document or msg.photo or msg.sticker or
        msg.animation
    )
    return has_text and not is_media


async def safe_edit_text(msg: Message, text: str, **kwargs) -> Message:
    """
    Умное редактирование сообщения.

    Если это текстовое сообщение — редактируем.
    Если это медиа (аудио/видео/фото) — отправляем новое.
    Если что-то пошло не так — тоже отправляем новое.

    Это ПОЛНОСТЬЮ решает ошибку 'There is no text in the message to edit'.
    """
    if is_editable(msg):
        try:
            return await msg.edit_text(text, **kwargs)
        except BadRequest as e:
            err = str(e)
            # Перехватываем все варианты этой ошибки
            if any(phrase in err for phrase in [
                "There is no text",
                "Message can't be edited",
                "Message is not modified",
            ]):
                pass  # fallback ниже
            else:
                raise  # другие BadRequest — пробрасываем
        except (TimedOut, RetryAfter):
            pass  # при таймаутах тоже fallback

    # Fallback — новое сообщение в тот же чат
    return await msg.reply_text(text, **kwargs)


# ══════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════

def kb_main() -> InlineKeyboardMarkup:
    """Главное меню."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 TikTok",  callback_data="info_tiktok"),
            InlineKeyboardButton("▶️ YouTube",  callback_data="info_youtube"),
            InlineKeyboardButton("📸 Insta",    callback_data="info_insta"),
        ],
        [
            InlineKeyboardButton("🎲 Сюрприз", callback_data="surprise"),
            InlineKeyboardButton("👤 Автор",   callback_data="author"),
            InlineKeyboardButton("❓ Помощь",  callback_data="help"),
        ],
    ])


def kb_back() -> InlineKeyboardMarkup:
    """Кнопка назад."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data="back_main"),
        InlineKeyboardButton("🏠 Меню",  callback_data="back_main"),
    ]])


def kb_download(url: str, platform: str) -> InlineKeyboardMarkup:
    """Кнопки выбора формата."""
    uid  = store_url(url)
    meta = PLATFORM_META.get(platform, PLATFORM_META["unknown"])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬  ВИДЕО", callback_data=f"dl_video|{uid}"),
            InlineKeyboardButton("🎵  АУДИО", callback_data=f"dl_audio|{uid}"),
        ],
        [
            InlineKeyboardButton(
                f"{meta['color']} {meta['label']}", callback_data="noop"
            ),
            InlineKeyboardButton("🏠 Меню", callback_data="back_main"),
        ],
    ])


def kb_after_download(uid: str, done_mode: str) -> InlineKeyboardMarkup:
    """
    Кнопки ПОСЛЕ скачивания — предлагаем второй формат.
    Эта клавиатура крепится к медиа-сообщению, поэтому
    при нажатии используем safe_edit_text (reply вместо edit).
    """
    other = "audio" if done_mode == "video" else "video"
    label = "🎵  АУДИО тоже" if other == "audio" else "🎬  ВИДЕО тоже"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"dl_{other}|{uid}")],
        [
            InlineKeyboardButton("🔁 Ещё ссылку", callback_data="back_main"),
            InlineKeyboardButton("🏠 Меню",        callback_data="back_main"),
        ],
    ])


# ══════════════════════════════════════════════════════════
#  АНИМАЦИЯ ЗАГРУЗКИ
# ══════════════════════════════════════════════════════════

LOADING_FRAMES = [
    ("⣾", "░░░░░░░░░░", " 0%"),
    ("⣽", "██░░░░░░░░", "20%"),
    ("⣻", "████░░░░░░", "40%"),
    ("⢿", "██████░░░░", "60%"),
    ("⣯", "████████░░", "80%"),
    ("✅", "██████████", "100%"),
]


async def animate(status_msg: Message, mode: str) -> None:
    """Анимируем прогресс-бар пока идёт скачивание."""
    title = "🎬 Качаю видос..." if mode == "video" else "🎵 Рву аудио..."
    for spin, bar, pct in LOADING_FRAMES:
        try:
            await status_msg.edit_text(
                f"{title}\n\n`{bar}` {pct}\n{spin}  обрабатываю...",
                parse_mode="Markdown",
            )
            await asyncio.sleep(0.5)
        except Exception:
            pass   # если не удалось обновить — просто пропускаем кадр


# ══════════════════════════════════════════════════════════
#  КОНТЕНТ ДЛЯ СООБЩЕНИЙ
# ══════════════════════════════════════════════════════════

SURPRISES = [
    "💀 Тихо скачал — никто не узнал.",
    "⚡ Быстро, грязно, эффективно.",
    "🌚 Скачал. Посмотрел. Никому не сказал.",
    "🔥 Го ещё одно!",
    "🎲 Удача на твоей стороне.",
    "🦁 Лев не спрашивает разрешения.",
    "🕶️ Смотришь со стилем.",
    "🐍 Тихий, как змея.",
    "🧠 Умный ход.",
    "💾 Сохранено в вечность. Почти.",
]

PLATFORM_INFO = {
    "info_tiktok": (
        "🎵 *TikTok*\n\n"
        "Поддерживаемые ссылки:\n"
        "• tiktok.com/@user/video/...\n"
        "• vm.tiktok.com/...\n"
        "• vt.tiktok.com/...\n\n"
        "🛡 Используется мобильный UA + спец. заголовки\n"
        "✅ Работает без авторизации"
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
        "⚠️ Приватные аккаунты и Сторис\n"
        "   требуют авторизации"
    ),
}

SURPRISE_TEXTS = [
    ("🎰", "Слот дня",       "🍒 🍒 🍒  — ДЖЕКПОТ!\nСкачай что-нибудь — заслужил."),
    ("🎱", "8-ball говорит", "Все знаки указывают — *да*."),
    ("🔮", "Пророчество",    "Сегодня скачаешь что-то эпичное."),
    ("⚡", "Факт",           "yt-dlp скачал больше видео,\nчем ты посмотрел за всю жизнь."),
    ("🌌", "Космос",         "Где-то во вселенной кто-то тоже\nкачает TikTok прямо сейчас."),
    ("🎭", "Театр абсурда",  "Ты нажал на сюрприз.\nЭто и был сюрприз. Конец."),
    ("🦁", "Мудрость",       "Лев не спрашивает разрешения.\nКидай ссылку."),
    ("🧿", "Защита",         "Бот защищает тебя\nот скучного контента."),
]


# ══════════════════════════════════════════════════════════
#  КОМАНДЫ
# ══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "бро"
    await update.message.reply_text(
        "╔══════════════════════╗\n"
        "║  🔥  SAVAGE DOWNLOAD  ║\n"
        "╚══════════════════════╝\n\n"
        f"Слышь, *{name}* 👋\n"
        "Кидай ссылку — я решу вопрос\n"
        "TikTok / YouTube / Insta — без разницы\n\n"
        "_Просто скинь ссылку и выбери формат_ 👇\n\n"
        f"`{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_main(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ffmpeg_s = "✅ MP3 (192 kbps)" if FFMPEG_OK else "❌ нет → аудио в M4A"
    proxy_s  = f"✅ `{PROXY.split('@')[-1]}`" if PROXY else "❌ выключен"
    await update.message.reply_text(
        "❓ *Помощь*\n\n"
        "┌─ Как использовать\n"
        "│  1. Отправь ссылку в чат\n"
        "│  2. Нажми ВИДЕО или АУДИО\n"
        "│  3. Жди — бот скачает!\n"
        "└──────────────────────\n\n"
        "📌 *Платформы:*\n"
        "🎵  TikTok\n"
        "▶️   YouTube / Shorts\n"
        "📸  Instagram Reels\n\n"
        "📥 *Форматы:*\n"
        "🎬  Видео → MP4\n"
        "🎵  Аудио → MP3 или M4A\n\n"
        "🛡 *Антибан:*\n"
        f"└ Прокси: {proxy_s}\n"
        f"└ FFmpeg: {ffmpeg_s}\n"
        f"└ Ретраи: {RETRY_COUNT}×\n"
        f"└ Задержки: {DELAY_MIN}–{DELAY_MAX} сек\n"
        f"└ UA-пул: {len(UA_DESKTOP)+len(UA_MOBILE)+len(UA_TIKTOK_APP)} агентов\n\n"
        f"`{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /status — полный дашборд антибан-системы."""
    ffmpeg_s = "✅ работает" if FFMPEG_OK else "❌ не найден"
    proxy_s  = f"✅ `{PROXY.split('@')[-1]}`" if PROXY else "❌ не настроен"
    ua_now   = pick_ua()[:58] + "…"

    await update.message.reply_text(
        "🛡 *Статус системы*\n\n"
        "┌─ Антибан ──────────────────\n"
        f"│ Прокси:     {proxy_s}\n"
        f"│ UA-ротация: ✅ ({len(UA_DESKTOP)+len(UA_MOBILE)+len(UA_TIKTOK_APP)} агентов)\n"
        f"│ Задержки:   ✅ ({DELAY_MIN}–{DELAY_MAX} сек)\n"
        f"│ Ретраи:     ✅ ({RETRY_COUNT} попытки)\n"
        f"│ Гео-обход:  ✅ (US)\n"
        "│\n"
        "├─ Система ──────────────────\n"
        f"│ FFmpeg:     {ffmpeg_s}\n"
        f"│ Сохранённых URL: {len(URL_STORE)}\n"
        "│\n"
        "├─ Текущий User-Agent ───────\n"
        f"│ `{ua_now}`\n"
        "└────────────────────────────\n\n"
        "💡 *Как включить прокси:*\n"
        "Открой `bot.py`, найди строку:\n"
        "`PROXY = None`\n"
        "Замени на:\n"
        "`PROXY = \"socks5://user:pass@ip:port\"`",
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


async def cmd_surprise(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    icon, title, text = random.choice(SURPRISE_TEXTS)
    await update.message.reply_text(
        f"{icon} *{title}*\n\n{text}\n\n`{AUTHOR}`",
        parse_mode="Markdown",
        reply_markup=kb_back(),
    )


# ══════════════════════════════════════════════════════════
#  ОБРАБОТЧИК СООБЩЕНИЙ
# ══════════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Ловим ссылки в любом сообщении."""
    text  = update.message.text or ""
    match = URL_RE.search(text)

    if not match:
        await update.message.reply_text(
            "🤔 *Не вижу ссылки...*\n\n"
            "Отправь ссылку на видео:\n"
            "TikTok / YouTube / Instagram 👇",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    platform = detect_platform(url)
    meta     = PLATFORM_META[platform]

    await update.message.reply_text(
        f"{meta['color']} *{meta['label']}* — поймал!\n\n"
        "Выбери формат 👇",
        parse_mode="Markdown",
        reply_markup=kb_download(url, platform),
    )


# ══════════════════════════════════════════════════════════
#  ОБРАБОТЧИК КНОПОК
# ══════════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()   # убираем "часики" у пользователя

    data = query.data
    msg  = query.message   # ВАЖНО: может быть текст ИЛИ медиа-файл!
                           # Именно поэтому используем safe_edit_text везде

    # ── МЕНЮ ──────────────────────────────────────────────
    if data in ("back_main", "menu"):
        name = update.effective_user.first_name or "бро"
        await safe_edit_text(
            msg,
            "╔══════════════════════╗\n"
            "║  🔥  SAVAGE DOWNLOAD  ║\n"
            "╚══════════════════════╝\n\n"
            f"Слышь, *{name}* 👋\n"
            "Кидай ссылку — я решу вопрос\n"
            "TikTok / YouTube / Insta — без разницы",
            parse_mode="Markdown",
            reply_markup=kb_main(),
        )
        return

    # ── ЗАГЛУШКА (декоративные кнопки) ────────────────────
    if data == "noop":
        return

    # ── ИНФО О ПЛАТФОРМАХ ─────────────────────────────────
    if data in PLATFORM_INFO:
        await safe_edit_text(
            msg,
            PLATFORM_INFO[data],
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── СЮРПРИЗ ───────────────────────────────────────────
    if data == "surprise":
        icon, title, text = random.choice(SURPRISE_TEXTS)
        await safe_edit_text(
            msg,
            f"{icon} *{title}*\n\n{text}\n\n`{AUTHOR}`",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── АВТОР ─────────────────────────────────────────────
    if data == "author":
        await safe_edit_text(
            msg,
            f"👤 *Автор*\n\n"
            f"`{AUTHOR}`\n"
            f"t.me/{AUTHOR_CLEAN}\n\n"
            f"Сделал этот бот чтобы облегчить жизнь 🔥\n"
            f"Понравилось — поделись с другом!",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── ПОМОЩЬ ────────────────────────────────────────────
    if data == "help":
        ffmpeg_s = "✅ MP3" if FFMPEG_OK else "❌ M4A"
        proxy_s  = "✅ вкл" if PROXY else "❌ выкл"
        await safe_edit_text(
            msg,
            f"❓ *Помощь*\n\n"
            f"Скинь ссылку → выбери формат → готово\n\n"
            f"🎵 TikTok │ ▶️ YouTube │ 📸 Insta\n"
            f"🎬 ВИДЕО (MP4) │ 🎵 АУДИО (MP3/M4A)\n\n"
            f"🛡 Прокси: {proxy_s} │ FFmpeg: {ffmpeg_s}\n\n"
            f"`{AUTHOR}`",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    # ── СКАЧИВАНИЕ ────────────────────────────────────────
    if not data.startswith(("dl_video|", "dl_audio|")):
        return

    # Разбираем callback: "dl_video|uid" или "dl_audio|uid"
    mode, uid = data.split("|", 1)
    mode = mode[3:]   # "video" или "audio"

    url = get_url(uid)
    if not url:
        # URL устарел (бот перезапустился или прошло много времени)
        await safe_edit_text(
            msg,
            "❌ *Ссылка устарела*\n\n"
            "Отправь ссылку заново 👇",
            parse_mode="Markdown",
            reply_markup=kb_back(),
        )
        return

    platform = detect_platform(url)
    meta     = PLATFORM_META[platform]

    # ── Статусное сообщение ────────────────────────────────
    # Всегда отправляем НОВОЕ сообщение через reply_text.
    # Почему? Потому что msg может быть медиа-файлом (аудио/видео),
    # и edit_text на нём вызовет ошибку BadRequest.
    title_anim = "🎬 Качаю видос..." if mode == "video" else "🎵 Рву аудио..."
    status = await msg.reply_text(
        f"{title_anim}\n\n`░░░░░░░░░░`  0%\n⣾  запускаю...",
        parse_mode="Markdown",
    )

    # ── Запускаем анимацию и скачивание параллельно ────────
    anim_task = asyncio.create_task(animate(status, mode))
    file_path = await download_media(url, mode)
    anim_task.cancel()   # останавливаем анимацию

    # ── Скачивание не удалось ─────────────────────────────
    if not file_path or not file_path.exists():
        if "tiktok" in url:
            err_text = (
                "❌ *TikTok заблокировал запрос*\n\n"
                "Что попробовать:\n"
                "• Включи прокси в `bot.py` (строка `PROXY`)\n"
                "• Подожди 2–3 минуты и попробуй снова\n"
                "• Проверь что ссылка рабочая\n\n"
                "💡 Лучшие прокси: proxyscrape.com\n"
                "   или купи платный SOCKS5"
            )
        elif "instagram" in url:
            err_text = (
                "❌ *Instagram не отдал видео*\n\n"
                "Причины:\n"
                "• Приватный аккаунт\n"
                "• Видео удалено\n"
                "• Instagram заблокировал IP хостинга\n\n"
                "Попробуй включить прокси в `bot.py`"
            )
        else:
            err_text = (
                "❌ *Не смог скачать*\n\n"
                "Причины:\n"
                "• Видео удалено или приватное\n"
                "• Платформа заблокировала IP\n"
                "• Ссылка устарела\n\n"
                "Попробуй другую ссылку 👇"
            )
        await status.edit_text(err_text, parse_mode="Markdown", reply_markup=kb_back())
        return

    # ── Финальный кадр анимации ────────────────────────────
    try:
        await status.edit_text(
            f"{title_anim}\n\n`██████████` 100%\n✅  отправляю...",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # ── Отправляем файл ───────────────────────────────────
    try:
        chat_id   = msg.chat_id
        file_size = file_path.stat().st_size
        mb        = file_size / 1024 / 1024
        ext       = file_path.suffix.lower()
        surprise  = random.choice(SURPRISES)
        after_kb  = kb_after_download(uid, mode)

        # Telegram принимает максимум 50 МБ
        if mb > MAX_FILE_MB:
            await status.edit_text(
                f"⚠️ *Файл слишком большой* ({mb:.0f} МБ)\n\n"
                f"Telegram принимает до {MAX_FILE_MB} МБ.\n"
                f"Попробуй другое видео или более низкое качество.",
                parse_mode="Markdown",
                reply_markup=kb_back(),
            )
            file_path.unlink(missing_ok=True)
            return

        # Определяем тип файла для отправки
        audio_exts = {".mp3", ".m4a", ".ogg", ".opus", ".aac", ".flac", ".wav"}
        is_audio   = (mode == "audio") or (ext in audio_exts)

        # Красивый капшн
        format_label = (
            f"MP3 192kbps" if ext == ".mp3" else
            f"M4A" if ext == ".m4a" else
            f"MP4" if ext == ".mp4" else
            ext.upper().lstrip(".")
        )
        caption = (
            f"{'🎵 Аудио' if is_audio else '🎬 Видео'} готово!\n"
            f"┌──────────────────────\n"
            f"│ 📦 {mb:.1f} МБ  │  {format_label}\n"
            f"│ {meta['emoji']} {meta['label']}\n"
            f"└──────────────────────\n\n"
            f"{surprise}\n\n"
            f"`{AUTHOR}`"
        )

        with open(file_path, "rb") as f:
            if is_audio:
                await ctx.bot.send_audio(
                    chat_id      = chat_id,
                    audio        = f,
                    caption      = caption,
                    parse_mode   = "Markdown",
                    reply_markup = after_kb,
                )
            else:
                await ctx.bot.send_video(
                    chat_id           = chat_id,
                    video             = f,
                    caption           = caption,
                    parse_mode        = "Markdown",
                    supports_streaming= True,
                    reply_markup      = after_kb,
                )

        # Удаляем статусное сообщение после успешной отправки
        try:
            await status.delete()
        except Exception:
            pass

    except Exception as e:
        log.error("Ошибка отправки файла: %s", e)
        try:
            await status.edit_text(
                f"❌ *Ошибка при отправке*\n\n"
                f"`{str(e)[:150]}`\n\n"
                f"Попробуй ещё раз 👇",
                parse_mode   = "Markdown",
                reply_markup = kb_back(),
            )
        except Exception:
            pass

    finally:
        # Удаляем временный файл в любом случае
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════
#  ЗАПУСК БОТА
# ══════════════════════════════════════════════════════════

async def post_init(app: Application) -> None:
    """Устанавливаем команды в меню Telegram и логируем статус."""
    await app.bot.set_my_commands([
        BotCommand("start",    "🚀 Запуск"),
        BotCommand("help",     "❓ Помощь"),
        BotCommand("status",   "🛡 Статус антибана"),
        BotCommand("surprise", "🎲 Сюрприз"),
    ])

    proxy_info = (
        f"прокси: {PROXY.split('@')[-1]}" if PROXY
        else "без прокси (рекомендуем настроить для TikTok)"
    )
    ffmpeg_info = "FFmpeg ✅" if FFMPEG_OK else "FFmpeg ❌ (M4A режим)"

    log.info("━" * 55)
    log.info("  🔥 SAVAGE DOWNLOADER запущен!")
    log.info("  👤 Автор: %s", AUTHOR)
    log.info("  🔀 %s", proxy_info)
    log.info("  🎵 %s", ffmpeg_info)
    log.info("  🛡 UA-пул: %d агентов",
             len(UA_DESKTOP) + len(UA_MOBILE) + len(UA_TIKTOK_APP))
    log.info("  🔄 Ретраи: %d × (задержка %d сек)", RETRY_COUNT, RETRY_DELAY)
    log.info("━" * 55)


def main() -> None:
    """Точка входа."""
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("surprise", cmd_surprise))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message,
    ))

    log.info("🤖 Бот запущен, жду сообщения...")
    app.run_polling(
        drop_pending_updates=True,   # игнорируем старые сообщения при рестарте
        poll_interval=1,
    )


if __name__ == "__main__":
    main()
