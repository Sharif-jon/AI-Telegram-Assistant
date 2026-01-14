import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import google.generativeai as genai

load_dotenv()

# НАСТРОЙКИ (Вставляй ключи сюда)
BOT_TOKEN = "TOKEN"
GOOGLE_API_KEY = "API KEY"


# Проверка, что ключи не пустые (на всякий случай)
if not BOT_TOKEN or "твои_символы" in BOT_TOKEN:
    print("❌ ОШИБКА: Ты забыл вставить свой Telegram токен в код!")
    exit()
if not GOOGLE_API_KEY or "твои_символы" in GOOGLE_API_KEY:
    print("❌ ОШИБКА: Ты забыл вставить свой Google API ключ в код!")
    exit()

# Настройка Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel(model_name='models/gemini-2.5-flash')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- СЛОВАРЬ ДЛЯ ХРАНЕНИЯ ФАЙЛОВ ---
# Будем временно хранить id файлов, пока юзер выбирает кнопку
user_files = {}


# --- ФУНКЦИЯ АНАЛИЗА ---
async def analyze_media_with_gemini(file_path, prompt):
    try:
        video_file = genai.upload_file(path=file_path)
        while video_file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            video_file = genai.get_file(video_file.name)

        response = model.generate_content([video_file, prompt])
        genai.delete_file(video_file.name)
        return response.text
    except Exception as e:
        logging.error(f"Ошибка Gemini: {e}")
        return "Что-то пошло не так при анализе файла... 😔"


# --- КЛАВИАТУРА ---
def get_choice_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="💬 Ответь как друг", callback_data="mode_friend"),
        types.InlineKeyboardButton(text="📝 Перескажи кратко", callback_data="mode_summary")
    )
    return builder.as_markup()


# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Приветик! Присылай кружок или голосовое, а я выберу, что с ним сделать. 👇")


# Обработка кружков И голосовых
@dp.message(F.video_note | F.voice)
async def handle_media(message: types.Message):
    file_id = message.video_note.file_id if message.video_note else message.voice.file_id

    # Сохраняем информацию о файле во временный словарь
    user_files[message.from_user.id] = {
        "file_id": file_id,
        "type": "video" if message.video_note else "audio"
    }

    await message.reply("Вижу сообщение! Что мне сделать?", reply_markup=get_choice_keyboard())


# Обработка нажатия кнопок
@dp.callback_query(F.data.startswith("mode_"))
async def process_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if user_id not in user_files:
        await callback.answer("Файл устарел или не найден. Пришли еще раз!")
        return

    mode = callback.data.split("_")[1]
    file_info = user_files[user_id]

    # Убираем кнопки и пишем статус
    await callback.message.edit_text("⏳ Думаю...")
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")

    # Скачивание
    file = await bot.get_file(file_info["file_id"])
    ext = "mp4" if file_info["type"] == "video" else "ogg"
    temp_filename = f"media_{user_id}.{ext}"

    try:
        await bot.download_file(file.file_path, temp_filename)

        # Настройка промпта в зависимости от выбора
        if mode == "friend":
            prompt = "Это сообщение от моего друга. Ответь ему ОДНИМ коротким, живым и неформальным сообщением как близкий кореш. Постебись или поддержи, будь естественным."
        else:
            prompt = "Сделай максимально краткий пересказ этого сообщения. Напиши только суть: о чем говорит человек и что происходит, чтобы я понял содержание, не смотря/не слушая полностью."

        ai_response = await analyze_media_with_gemini(temp_filename, prompt)

        # Результат
        await callback.message.edit_text(ai_response)

    except Exception as e:
        logging.error(e)
        await callback.message.edit_text("Произошла ошибка. 🤷‍♂️")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        # Очищаем память
        del user_files[user_id]


# Игнорируем обычный текст
@dp.message(F.text)
async def ignore_text(message: types.Message):
    pass


# --- ЗАПУСК ---
async def main():
    print("🚀 Бот-ассистент запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
