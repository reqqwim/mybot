#!/usr/bin/env python3
import os
import logging
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

conversation_history = {}

SYSTEM_PROMPT = "Ты умный и дружелюбный ИИ-ассистент в Telegram. Отвечай на русском языке если пользователь пишет по-русски. Будь полезным и кратким."


def get_gpt_response(user_id: int, user_message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_message})
    history = conversation_history[user_id][-20:]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        max_tokens=1024
    )

    reply = response.choices[0].message.content
    conversation_history[user_id].append({"role": "assistant", "content": reply})
    return reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я ИИ-ассистент на базе GPT-4o.\n\n"
        "✉️ Напиши текстовое сообщение или\n"
        "🎤 Отправь голосовое — отвечу на всё!\n\n"
        "/clear — очистить историю диалога"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history.pop(update.effective_user.id, None)
    await update.message.reply_text("🗑 История очищена!")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        response = get_gpt_response(update.effective_user.id, update.message.text)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("⚠️ Ошибка. Попробуй ещё раз.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

        with open(tmp_path, "rb") as audio:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=audio, language="ru")
        os.unlink(tmp_path)

        text = transcript.text
        await update.message.reply_text(f"🎤 Ты сказал: *{text}*", parse_mode="Markdown")

        response = get_gpt_response(update.effective_user.id, text)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка голоса: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке голосового.")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
