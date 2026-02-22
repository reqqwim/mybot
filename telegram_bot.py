#!/usr/bin/env python3
"""
Telegram Bot с интеграцией Claude AI
Отвечает на текстовые и голосовые сообщения

Установка зависимостей:
    pip install python-telegram-bot anthropic openai

Запуск:
    python telegram_bot.py
"""

import os
import logging
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# ============================================================
# НАСТРОЙКИ — заполни свои ключи здесь
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Получить Anthropic API ключ: https://console.anthropic.com/
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Клиент Anthropic (Claude)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Храним историю диалогов (в памяти)
conversation_history: dict[int, list] = {}

SYSTEM_PROMPT = """Ты умный и дружелюбный ИИ-ассистент в Telegram. 
Отвечай на русском языке, если пользователь пишет по-русски.
Будь полезным, точным и кратким."""


def get_claude_response(user_id: int, user_message: str) -> str:
    """Получить ответ от Claude с учётом истории диалога."""
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({
        "role": "user",
        "content": user_message
    })

    # Ограничиваем историю последними 20 сообщениями
    history = conversation_history[user_id][-20:]

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=history
    )

    assistant_message = response.content[0].text

    conversation_history[user_id].append({
        "role": "assistant",
        "content": assistant_message
    })

    return assistant_message


async def transcribe_voice(file_path: str) -> str:
    """Транскрибировать голосовое сообщение через OpenAI Whisper."""
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        with open(file_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        return transcript.text
    except Exception as e:
        logger.error(f"Ошибка транскрипции: {e}")
        return None


# ==================== Обработчики ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я ИИ-ассистент на базе Claude (Anthropic).\n\n"
        "✉️ Напиши мне текстовое сообщение или\n"
        "🎤 Отправь голосовое — я всё пойму и отвечу!\n\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/clear — очистить историю диалога"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history.pop(user_id, None)
    await update.message.reply_text("🗑 История диалога очищена!")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = get_claude_response(user_id, user_text)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка Claude: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуй ещё раз.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("🎤 Обрабатываю голосовое сообщение...")

    try:
        # Скачиваем голосовое сообщение
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await voice_file.download_to_drive(tmp_path)

        # Транскрибируем
        transcribed_text = await transcribe_voice(tmp_path)
        os.unlink(tmp_path)

        if not transcribed_text:
            await update.message.reply_text(
                "⚠️ Не удалось распознать голос. "
                "Для голосовых сообщений нужен OPENAI_API_KEY (Whisper)."
            )
            return

        await update.message.reply_text(f"📝 Ты сказал: *{transcribed_text}*", parse_mode="Markdown")

        # Получаем ответ Claude
        response = get_claude_response(user_id, transcribed_text)
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Ошибка обработки голоса: {e}")
        await update.message.reply_text("⚠️ Ошибка при обработке голосового сообщения.")


# ==================== Запуск ====================

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
