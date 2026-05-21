import os
import fal_client
import tempfile
import requests
import io
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
FAL_KEY = os.environ.get("FAL_KEY")

# ─── Limit Per User ───
user_usage = {}
IMAGE_LIMIT = 1000

def get_usage(user_id):
    if user_id not in user_usage:
        user_usage[user_id] = {"image": 0}
    return user_usage[user_id]

def check_limit(user_id):
    return get_usage(user_id)["image"] < IMAGE_LIMIT

def increment_usage(user_id):
    get_usage(user_id)
    user_usage[user_id]["image"] += 1

# ─── Upload gambar ke fal ───
async def upload_image_to_fal(update: Update, context):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    response = requests.get(file.file_path)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    image_url = fal_client.upload_file(tmp_path)
    os.remove(tmp_path)
    return image_url

# ─── Generate Image ───
def generate_image(prompt, image_urls):
    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                print(log["message"])

    result = fal_client.subscribe(
        "fal-ai/bytedance/seedream/v4.5/edit",
        arguments={
            "prompt": prompt,
            "image_urls": image_urls
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return result

# ─── Handler /start ───
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 *Image Edit Bot*\n\n"
        "Hantar gambar dengan caption sebagai prompt!\n\n"
        "Contoh:\n"
        "• Hantar gambar + caption `replace background with sunset`\n"
        "• Hantar gambar + caption `make it look like winter`\n\n"
        "📊 Semak usage: /usage",
        parse_mode="Markdown"
    )

# ─── Handler /usage ───
async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_usage(user_id)
    await update.message.reply_text(
        f"📊 *Usage Awak:*\n\n"
        f"🎨 Image: {u['image']}/{IMAGE_LIMIT}",
        parse_mode="Markdown"
    )

# ─── Handler gambar + caption ───
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Semak ada caption tak
    prompt = update.message.caption
    if not prompt:
        await update.message.reply_text(
            "⚠️ Sila hantar gambar dengan caption sebagai prompt!\n\n"
            "Contoh: hantar gambar + caption `replace background with sunset`"
        )
        return

    if not check_limit(user_id):
        await update.message.reply_text(f"❌ Had image awak dah penuh! ({IMAGE_LIMIT} gambar)")
        return

    await update.message.reply_text("⏳ Sedang proses gambar...")

    try:
        # Upload gambar
        image_url = await upload_image_to_fal(update, context)

        # Terus generate
        result = generate_image(prompt, [image_url])
        img_url = result["images"][0]["url"]

        increment_usage(user_id)
        u = get_usage(user_id)

        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_url,
            caption=f"✨ {prompt}\n\n🎨 {u['image']}/{IMAGE_LIMIT}"
        )

    except Exception as e:
        print("Error:", e)
        await update.message.reply_text(f"❌ Gagal proses gambar.\n\nError: {e}")

# ─── Handler teks biasa ───
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Hantar gambar dengan caption untuk edit!\n\n"
        "Contoh: hantar gambar + caption `replace background with sunset`"
    )

# ─── Run Bot ───
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("usage", usage))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Image Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
