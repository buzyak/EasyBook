from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from backend.config import settings


dp = Dispatcher()


def app_keyboard(label: str = "✨ Открыть EasyBook"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=label,
            web_app=WebAppInfo(url=f"{settings.public_base_url.rstrip('/')}/app/")
        )
    ]])


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Добро пожаловать в EasyBook 👋\n\nОткрой Mini App, чтобы записаться или управлять бизнесом.",
        reply_markup=app_keyboard(),
    )


@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != settings.owner_telegram_id:
        return
    await message.answer("Панель EasyBook:", reply_markup=app_keyboard("⚙️ Открыть панель"))


async def start_bot():
    bot = Bot(settings.bot_token)
    await dp.start_polling(bot)
