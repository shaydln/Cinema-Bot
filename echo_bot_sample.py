from aiogram import Bot, types
from aiogram import Dispatcher, executor

__BOT_TOKEN = '6914059007:AAEgDkw1YRea1cTo7mwQ1a0GjD1-lqD-3PY'

bot = Bot(token=__BOT_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Hello, i'm Cinema Bot!")


if __name__ == '__main__':
    executor.start_polling(dp)
