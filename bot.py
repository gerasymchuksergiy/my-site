import os
import re
import logging
import tempfile
import asyncio
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TIKTOK_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(vm\.tiktok\.com|tiktok\.com|vt\.tiktok\.com)/\S+"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


def is_tiktok_url(text: str) -> bool:
    return bool(TIKTOK_URL_PATTERN.search(text))


def extract_tiktok_url(text: str) -> str | None:
    match = TIKTOK_URL_PATTERN.search(text)
    return match.group(0) if match else None


async def download_tiktok(url: str, output_dir: str) -> str:
    ydl_opts = {
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        # Download without watermark via TikTok API endpoint
        "extractor_args": {
            "tiktok": {
                "api_hostname": "api22-normal-c-useast2a.tiktokv.com",
                "app_version": "20.1.0",
            }
        },
    }

    loop = asyncio.get_event_loop()

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # yt-dlp may change extension after merge
            path = Path(filename)
            if not path.exists():
                mp4_path = path.with_suffix(".mp4")
                if mp4_path.exists():
                    return str(mp4_path)
                # find any downloaded file
                files = list(Path(output_dir).iterdir())
                if files:
                    return str(files[0])
                raise FileNotFoundError("Downloaded file not found")
            return str(path)

    return await loop.run_in_executor(None, _download)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привіт! Надішли мені посилання на TikTok відео, і я завантажу його без вотермарки.\n\n"
        "Просто встав посилання у чат — бот зробить усе сам."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Як користуватись:\n"
        "1. Скопіюй посилання на TikTok відео\n"
        "2. Надішли його сюди\n"
        "3. Отримай відео без вотермарки\n\n"
        "Підтримуються посилання форматів:\n"
        "• https://tiktok.com/@user/video/...\n"
        "• https://vm.tiktok.com/...\n"
        "• https://vt.tiktok.com/..."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    if not is_tiktok_url(text):
        await update.message.reply_text(
            "Це не схоже на TikTok посилання. Надішли коректне посилання на відео."
        )
        return

    url = extract_tiktok_url(text)
    status_msg = await update.message.reply_text("Завантажую відео...")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            video_path = await download_tiktok(url, tmpdir)

            file_size = os.path.getsize(video_path)
            # Telegram bot API limit is 50 MB
            if file_size > 50 * 1024 * 1024:
                await status_msg.edit_text(
                    "Відео завелике для відправки через Telegram (максимум 50 МБ)."
                )
                return

            await status_msg.edit_text("Відправляю відео...")
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    supports_streaming=True,
                )
            await status_msg.delete()

        except yt_dlp.utils.DownloadError as e:
            logger.error("Download error: %s", e)
            await status_msg.edit_text(
                "Не вдалося завантажити відео. Перевір посилання або спробуй пізніше."
            )
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            await status_msg.edit_text("Сталася помилка. Спробуй ще раз.")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
