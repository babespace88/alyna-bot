import os
import logging
import base64
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import anthropic
from datetime import datetime

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MONTHLY_CHAT_LIMIT = int(os.environ.get("MONTHLY_CHAT_LIMIT", 100))
ACCESS_KEYWORD    = "1188"   # ← keyword wajib untuk masuk

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Store (in-memory — ganti PostgreSQL untuk production) ─
approved_users: set[int] = set()          # user yg dah verify keyword
user_usage: dict[int, dict] = {}          # track penggunaan bulanan

# ── Helper: semak & urus akses ───────────────────────────
def is_approved(user_id: int) -> bool:
    return user_id in approved_users

def approve_user(user_id: int):
    approved_users.add(user_id)

# ── Helper: usage tracker ────────────────────────────────
def get_usage(user_id: int) -> dict:
    now = datetime.now()
    if user_id not in user_usage:
        user_usage[user_id] = {"count": 0, "month": now.month, "year": now.year}
    u = user_usage[user_id]
    # Reset automatik bila bulan baru
    if u["month"] != now.month or u["year"] != now.year:
        u["count"] = 0
        u["month"] = now.month
        u["year"] = now.year
    return u

def increment_usage(user_id: int):
    get_usage(user_id)["count"] += 1

def is_limit_reached(user_id: int) -> bool:
    return get_usage(user_id)["count"] >= MONTHLY_CHAT_LIMIT

# ── System Prompt ─────────────────────────────────────────
SYSTEM_PROMPT = """Kamu adalah ScamDetect AI — pakar forensik penipuan digital untuk pasaran Malaysia.

TUGAS UTAMA:
1. DETECT SCAMMER DARI CHAT/TEKS
   - Kenal pasti asal negara/wilayah scammer berdasarkan:
     * Corak bahasa, ejaan, tatabahasa
     * Slanga atau perkataan unik
     * Struktur ayat dan gaya penulisan
   - Senaraikan red flags penipuan yang ditemui
   - Berikan tahap risiko: RENDAH / SEDERHANA / TINGGI / KRITIKAL

2. DETECT RESIT/CEKUE BANK PALSU (dari gambar)
   - Semak ketulenan resit bank, slip pembayaran, cekue
   - Kenal pasti tanda-tanda pemalsuan:
     * Font tidak konsisten
     * Watermark atau logo tidak betul
     * Nombor akaun, tarikh, atau jumlah yang mencurigakan
     * Kualiti imej atau cetakan
   - PENTING: Jika resit/cekue mencurigakan atau palsu:
     * Beritahu pemilik untuk TUNGGU 5-10 hari bekerja sebelum release barang/perkhidmatan
     * Selepas tempoh tersebut, hubungi bank untuk pengesahan muktamad
     * Jangan sesekali percaya 100% pada resit sebelum pengesahan bank

FORMAT JAWAPAN:
🔍 ANALISIS: [ringkasan]
🌍 ASAL SCAMMER: [negara/wilayah jika berkaitan]
⚠️ RED FLAGS: [senarai]
🎯 TAHAP RISIKO: [RENDAH/SEDERHANA/TINGGI/KRITIKAL]
💡 NASIHAT: [tindakan yang perlu diambil]

Sentiasa jawab dalam Bahasa Malaysia. Bersikap tegas tapi profesional."""

# ── GUARD: semak akses sebelum buat apa-apa ─────────────
async def check_access(update: Update) -> bool:
    """Return True kalau user boleh guna bot. False = reject & inform."""
    uid = update.effective_user.id
    if is_approved(uid):
        return True
    await update.message.reply_text(
        "🔐 *Akses Ditolak*\n\n"
        "Bot ini adalah perkhidmatan berbayar.\n"
        "Sila masukkan *kod akses* anda untuk teruskan.\n\n"
        "Belum ada kod akses? Hubungi admin.",
        parse_mode="Markdown"
    )
    return False

# ── /start ────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_approved(uid):
        await update.message.reply_text(
            "✅ *Anda sudah log masuk ke ScamDetect AI!*\n\n"
            "📱 Hantar *teks/screenshot chat* → detect scammer\n"
            "🧾 Hantar *gambar resit/cekue* → semak ketulenan\n\n"
            f"⚡ Had: *{MONTHLY_CHAT_LIMIT} analisis/bulan*\n"
            "Taip /status untuk semak baki analisis.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🔐 *ScamDetect AI — Akses Diperlukan*\n\n"
            "Bot ini adalah *perkhidmatan berbayar* dan tidak terbuka kepada umum.\n\n"
            "Sila masukkan *kod akses* anda untuk teruskan.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Belum ada kod akses? Hubungi admin.",
            parse_mode="Markdown"
        )

# ── /status ───────────────────────────────────────────────
async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return
    uid = update.effective_user.id
    u = get_usage(uid)
    remaining = MONTHLY_CHAT_LIMIT - u["count"]
    await update.message.reply_text(
        f"📊 *Status Penggunaan Anda*\n\n"
        f"✅ Digunakan: {u['count']}/{MONTHLY_CHAT_LIMIT}\n"
        f"🔋 Baki: {remaining} analisis\n"
        f"📅 Reset: Awal bulan depan",
        parse_mode="Markdown"
    )

# ── /help ─────────────────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        return
    await update.message.reply_text(
        "📖 *Panduan ScamDetect AI*\n\n"
        "*Untuk detect scammer:*\n"
        "Hantar teks atau screenshot percakapan yang mencurigakan\n\n"
        "*Untuk semak resit/cekue:*\n"
        "Hantar gambar resit bank, slip pembayaran, atau cekue\n\n"
        "*Peringatan penting:*\n"
        "⏳ Tunggu 5-10 hari bekerja sebelum release barang\n"
        "📞 Hubungi bank untuk pengesahan muktamad\n\n"
        "*Commands:*\n"
        "/start — Mulakan bot\n"
        "/status — Semak baki analisis\n"
        "/help — Panduan penggunaan",
        parse_mode="Markdown"
    )

# ── Handle teks (keyword check + analisis) ───────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # ① Semak keyword 1188 kalau belum approved
    if not is_approved(uid):
        if text == ACCESS_KEYWORD:
            approve_user(uid)
            await update.message.reply_text(
                "✅ *Kod akses diterima! Selamat datang ke ScamDetect AI.*\n\n"
                "📱 Hantar *teks/screenshot chat* → detect scammer\n"
                "🧾 Hantar *gambar resit/cekue* → semak ketulenan\n\n"
                f"⚡ Had: *{MONTHLY_CHAT_LIMIT} analisis/bulan*\n"
                "Taip /help untuk panduan lengkap.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❌ *Kod akses salah.*\n\n"
                "Sila masukkan kod akses yang betul.\n"
                "Hubungi admin jika anda belum mempunyai kod akses.",
                parse_mode="Markdown"
            )
        return

    # ② Semak had bulanan
    if is_limit_reached(uid):
        await update.message.reply_text(
            "❌ *Had bulanan anda telah habis.*\n\n"
            "Had anda akan reset pada awal bulan depan.\n"
            "Hubungi admin untuk naik taraf pelan.",
            parse_mode="Markdown"
        )
        return

    # ③ Analisis teks/chat
    thinking = await update.message.reply_text(
        "🔍 *Menganalisis teks...* Sila tunggu.", parse_mode="Markdown"
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Sila analisis teks/chat berikut untuk detect penipuan:\n\n{text}"
            }]
        )
        result = response.content[0].text
        increment_usage(uid)
        remaining = MONTHLY_CHAT_LIMIT - get_usage(uid)["count"]

        await thinking.edit_text(
            f"{result}\n\n─────────────────\n"
            f"🔋 Baki analisis: {remaining}/{MONTHLY_CHAT_LIMIT}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Text analysis error: {e}")
        await thinking.edit_text("⚠️ Ralat semasa menganalisis. Sila cuba lagi.")

# ── Handle gambar (resit/cekue) ───────────────────────────
async def handle_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Semak akses dulu
    if not is_approved(uid):
        await update.message.reply_text(
            "🔐 *Akses Ditolak*\n\n"
            "Sila masukkan *kod akses* anda dahulu.",
            parse_mode="Markdown"
        )
        return

    # Semak had bulanan
    if is_limit_reached(uid):
        await update.message.reply_text(
            "❌ *Had bulanan anda telah habis.*\n\n"
            "Had anda akan reset pada awal bulan depan.",
            parse_mode="Markdown"
        )
        return

    thinking = await update.message.reply_text(
        "🔍 *Menganalisis gambar...* Sila tunggu.", parse_mode="Markdown"
    )

    try:
        photo    = update.message.photo[-1] if update.message.photo else None
        document = update.message.document if update.message.document else None

        if photo:
            file = await ctx.bot.get_file(photo.file_id)
        elif document and document.mime_type and document.mime_type.startswith("image/"):
            file = await ctx.bot.get_file(document.file_id)
        else:
            await thinking.edit_text("⚠️ Sila hantar gambar yang sah (JPG/PNG).")
            return

        file_bytes = await file.download_as_bytearray()
        image_b64  = base64.standard_b64encode(file_bytes).decode("utf-8")
        caption    = update.message.caption or ""

        user_prompt = (
            "Sila analisis gambar resit/cekue/dokumen ini untuk detect penipuan."
            + (f"\nNota tambahan dari pengguna: {caption}" if caption else "")
        )

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64
                        }
                    },
                    {"type": "text", "text": user_prompt}
                ]
            }]
        )

        result    = response.content[0].text
        increment_usage(uid)
        remaining = MONTHLY_CHAT_LIMIT - get_usage(uid)["count"]

        await thinking.edit_text(
            f"{result}\n\n─────────────────\n"
            f"🔋 Baki analisis: {remaining}/{MONTHLY_CHAT_LIMIT}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        await thinking.edit_text("⚠️ Ralat semasa menganalisis gambar. Sila cuba lagi.")

# ── Main ──────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help",   help_cmd))

    # Semua teks (termasuk keyword 1188) dihandle sini
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    # Gambar resit/cekue
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))

    logger.info("🤖 ScamDetect Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
