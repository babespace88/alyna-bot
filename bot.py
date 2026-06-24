import os
import logging
import base64
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import anthropic

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MONTHLY_CHAT_LIMIT = int(os.environ.get("MONTHLY_CHAT_LIMIT", 100))
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak dijumpai dalam environment variable")

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY tidak dijumpai dalam environment variable")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── In-memory usage tracker ──────────────────────────────
user_usage = {}

def get_usage(user_id: int) -> dict:
    now = datetime.now()

    if user_id not in user_usage:
        user_usage[user_id] = {
            "count": 0,
            "month": now.month,
            "year": now.year,
        }

    usage = user_usage[user_id]

    if usage["month"] != now.month or usage["year"] != now.year:
        usage["count"] = 0
        usage["month"] = now.month
        usage["year"] = now.year

    return usage

def increment_usage(user_id: int):
    usage = get_usage(user_id)
    usage["count"] += 1

def is_limit_reached(user_id: int) -> bool:
    return get_usage(user_id)["count"] >= MONTHLY_CHAT_LIMIT

# ── System Prompt ────────────────────────────────────────
SYSTEM_PROMPT = """
Kamu adalah ScamDetect AI — pakar forensik penipuan digital untuk pasaran Malaysia.

TUGAS UTAMA:

1. DETECT SCAMMER DARI CHAT/TEKS
- Kenal pasti asal negara/wilayah scammer berdasarkan corak bahasa, ejaan, tatabahasa, slanga, struktur ayat dan gaya penulisan.
- Senaraikan red flags penipuan.
- Berikan tahap risiko: RENDAH / SEDERHANA / TINGGI / KRITIKAL.

2. DETECT RESIT / CEK / SLIP BANK PALSU DARI GAMBAR
- Semak ketulenan resit bank, slip pembayaran atau cek.
- Kenal pasti tanda pemalsuan seperti font tidak konsisten, logo pelik, watermark salah, nombor akaun mencurigakan, tarikh/jumlah tidak masuk akal, atau kualiti imej mencurigakan.
- Jika resit mencurigakan, nasihatkan pemilik untuk tunggu 5-10 hari bekerja sebelum release barang/perkhidmatan.
- Nasihatkan pengguna hubungi bank untuk pengesahan muktamad.

FORMAT JAWAPAN:

🔍 ANALISIS:
🌍 ASAL SCAMMER:
⚠️ RED FLAGS:
🎯 TAHAP RISIKO:
💡 NASIHAT:

Sentiasa jawab dalam Bahasa Malaysia. Bersikap tegas tapi profesional.
"""

# ── Helpers ──────────────────────────────────────────────
def get_text_from_claude(response) -> str:
    texts = []

    for block in response.content:
        if hasattr(block, "text"):
            texts.append(block.text)

    return "\n".join(texts).strip() or "Maaf, tiada jawapan diterima daripada AI."

def safe_remaining(user_id: int) -> int:
    usage = get_usage(user_id)
    return max(MONTHLY_CHAT_LIMIT - usage["count"], 0)

# ── Handlers ─────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Selamat datang ke ScamDetect AI!\n\n"
        "Saya boleh membantu anda:\n"
        "📱 Detect scammer dari teks/chat\n"
        "🧾 Semak resit, slip bank atau cek palsu\n\n"
        "Cara guna:\n"
        "• Hantar teks chat mencurigakan\n"
        "• Hantar gambar resit/slip bank/cek\n\n"
        f"⚡ Had: {MONTHLY_CHAT_LIMIT} analisis/bulan\n\n"
        "Taip /status untuk semak baki analisis anda."
    )

    await update.message.reply_text(text)

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    usage = get_usage(user_id)
    remaining = safe_remaining(user_id)

    text = (
        "📊 Status Penggunaan Anda\n\n"
        f"✅ Digunakan: {usage['count']}/{MONTHLY_CHAT_LIMIT}\n"
        f"🔋 Baki: {remaining} analisis\n"
        "📅 Reset: Awal bulan depan"
    )

    await update.message.reply_text(text)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Panduan ScamDetect AI\n\n"
        "Untuk detect scammer:\n"
        "Hantar teks atau screenshot percakapan yang mencurigakan.\n\n"
        "Untuk semak resit/slip bank/cek:\n"
        "Hantar gambar resit bank, slip pembayaran atau cek.\n\n"
        "Peringatan penting:\n"
        "⏳ Untuk resit/slip mencurigakan, tunggu 5-10 hari bekerja sebelum release barang.\n"
        "📞 Hubungi bank untuk pengesahan muktamad.\n\n"
        "Commands:\n"
        "/start - Mulakan bot\n"
        "/status - Semak baki analisis\n"
        "/help - Panduan penggunaan"
    )

    await update.message.reply_text(text)

async def analyze_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_limit_reached(user_id):
        await update.message.reply_text(
            "❌ Had bulanan anda telah habis.\n\n"
            "Had anda akan reset pada awal bulan depan.\n"
            "Hubungi admin untuk naik taraf pelan."
        )
        return

    user_text = update.message.text or ""

    if not user_text.strip():
        await update.message.reply_text("⚠️ Sila hantar teks yang ingin dianalisis.")
        return

    thinking_msg = await update.message.reply_text("🔍 Menganalisis teks... Sila tunggu.")

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Sila analisis teks/chat berikut untuk detect penipuan:\n\n{user_text}",
                }
            ],
        )

        result = get_text_from_claude(response)

        increment_usage(user_id)
        remaining = safe_remaining(user_id)

        await thinking_msg.edit_text(
            f"{result}\n\n─────────────────\n"
            f"🔋 Baki analisis: {remaining}/{MONTHLY_CHAT_LIMIT}"
        )

    except Exception as e:
        logger.exception("Error analyzing text")
        await thinking_msg.edit_text(
            f"⚠️ Ralat semasa menganalisis teks.\n\nError: {str(e)[:300]}"
        )

async def analyze_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_limit_reached(user_id):
        await update.message.reply_text(
            "❌ Had bulanan anda telah habis.\n\n"
            "Had anda akan reset pada awal bulan depan."
        )
        return

    thinking_msg = await update.message.reply_text("🔍 Menganalisis gambar... Sila tunggu.")

    try:
        photo = update.message.photo[-1] if update.message.photo else None
        document = update.message.document if update.message.document else None

        media_type = "image/jpeg"
        telegram_file = None

        if photo:
            telegram_file = await ctx.bot.get_file(photo.file_id)
            media_type = "image/jpeg"

        elif document and document.mime_type and document.mime_type.startswith("image/"):
            telegram_file = await ctx.bot.get_file(document.file_id)
            media_type = document.mime_type

        else:
            await thinking_msg.edit_text("⚠️ Sila hantar gambar yang sah seperti JPG atau PNG.")
            return

        file_bytes = await telegram_file.download_as_bytearray()
        image_b64 = base64.b64encode(file_bytes).decode("utf-8")

        caption = update.message.caption or ""

        user_prompt = "Sila analisis gambar ini untuk detect resit/slip bank/cek palsu atau tanda penipuan."

        if caption.strip():
            user_prompt += f"\n\nNota tambahan pengguna: {caption}"

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": user_prompt,
                        },
                    ],
                }
            ],
        )

        result = get_text_from_claude(response)

        increment_usage(user_id)
        remaining = safe_remaining(user_id)

        await thinking_msg.edit_text(
            f"{result}\n\n─────────────────\n"
            f"🔋 Baki analisis: {remaining}/{MONTHLY_CHAT_LIMIT}"
        )

    except Exception as e:
        logger.exception("Error analyzing image")
        await thinking_msg.edit_text(
            f"⚠️ Ralat semasa menganalisis gambar.\n\nError: {str(e)[:300]}"
        )

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.exception("Telegram error", exc_info=ctx.error)

# ── Main ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, analyze_image))

    app.add_error_handler(error_handler)

    logger.info("🤖 ScamDetect Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
