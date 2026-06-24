import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

print("TELEGRAM_TOKEN EXISTS:", bool(TELEGRAM_TOKEN))
print("ANTHROPIC_API_KEY EXISTS:", bool(ANTHROPIC_API_KEY))

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN missing")

client = None
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot hidup ✅")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if client is None:
        await update.message.reply_text(
            "Bot hidup ✅ tapi ANTHROPIC_API_KEY belum detect dekat Railway Variables."
        )
        return

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": text}],
        )

        reply = msg.content[0].text
        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"Claude error: {str(e)[:500]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("BOT STARTED ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
