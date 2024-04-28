import json
import logging
import re
import typing as tp

import aiohttp
import aiosqlite
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import Message
from kinopoisk_dev import KinopoiskDev, MovieParams, MovieField
from config import __KINOPOISK_TOKEN, __TELEGRAM_TOKEN, __THEMOVIEDB_TOKEN
from config import google_url, google_headers

bot = Bot(token=__TELEGRAM_TOKEN)
dp = Dispatcher(bot)


async def check_movie_existence(movie_title):
    url = f"https://watch.coocha.co/search/{movie_title.replace(' ', '+')}"
    try:
        async with (aiohttp.ClientSession() as session):
            async with session.get(url) as response:
                response.raise_for_status()
                html_content = await response.text()

                soup = BeautifulSoup(html_content, 'html.parser')
                movie_names_found = soup.find_all('h3', class_="new-short__title hover-op")

                for name_elem in movie_names_found:
                    if movie_title.replace("ё", "е").strip(
                    ).lower() == name_elem.get_text().replace("ё", "е").strip().lower():
                        return {
                            "url": name_elem.find_previous('a', class_="new-short__title--link")['href'],
                            "name": name_elem.get_text()
                        }

                return None
    except aiohttp.ClientError as e:
        logging.error(f"Error in HTTP request: {e}")
        return None
    except Exception as e:
        logging.error(f"Error processing response: {e}")
        return None


async def get_movie_info(title: str, is_cyrillic: bool):
    kp = KinopoiskDev(token=__KINOPOISK_TOKEN)
    params = [
        MovieParams(keys=MovieField.PAGE, value="1"),
        MovieParams(keys=MovieField.LIMIT, value="1"),
    ]

    name_param_key = MovieField.NAME if is_cyrillic else MovieField.ALTERNATIVE_NAME
    params.append(MovieParams(keys=name_param_key, value=title))

    try:
        items = await kp.afind_many_movie(params=params)
    except Exception as e:
        logging.error(f"Error getting movie info for '{title}': {e}")
        return None

    if items.docs:
        return {
            "Name": items.docs[0].name,
            "Year": items.docs[0].year,
            "Rating": items.docs[0].rating.imdb,
            "Description": items.docs[0].shortDescription,
            "Poster": items.docs[0].poster.url
        }
    else:
        return None


@dp.message_handler(commands=['start'])
async def send_welcome(message: Message):
    await message.reply("Привет я cinema bot ©shaydln, чтобы найти фильм напиши его название, а я попробую найти его"
                        "Если запутался напиши команду /help")


@dp.message_handler(commands=['stats'])
async def send_stats(message: Message):
    async with aiosqlite.connect('bot_db.db') as db:
        cursor = await db.execute(
            "SELECT film_name, COUNT(*) as count FROM search_history GROUP BY film_name ORDER BY count DESC LIMIT 10")
        rows = await cursor.fetchall()

        response_message = "Топ-10 поисковых запросов:\n"
        for row in rows:
            response_message += f"{row[0]}: {row[1]} раз(а)\n"

        await message.reply(response_message)


@dp.message_handler(commands=['pray'])
async def send_pray(message: Message):
    await message.reply("Дайте пожалуйста 250 баллов, чтобы защитать 1 дз по получить 3 🥺")
    await bot.send_photo(
        message.from_user.id,
        photo="https://upload.wikimedia.org/wikipedia/ru/thumb/1/16/%D0%9A%D0%BE%D1%82_%D0%B2_%D1%81%D0%B0%D0%BF%D0%BE%"
              "D0%B3%D0%B0%D1%85_%D1%81_%D1%80%D0%B0%D1%81%D1%88%D0%B8%D1%80%D0%B5%D0%BD%D0%BD%D1%8B%D0%BC%D0%B8_%D0%B7"
              "%D1%80%D0%B0%D1%87%D0%BA%D0%B0%D0%BC%D0%B8.jpg/440px-%D0%9A%D0%BE%D1%82_%D0%B2_%D1%81%D0%B0%D0%BF%D0%BE"
              "%D0%B3%D0%B0%D1%85_%D1%81_%D1%80%D0%B0%D1%81%D1%88%D0%B"
              "8%D1%80%D0%B5%D0%BD%D0%BD%D1%8B%D0%BC%D0%B8_%D0%B"
              "7%D1%80%D0%B0%D1%87%D0%BA%D0%B0%D0%BC%D0%B8.jpg"
    )


@dp.message_handler(commands=['help'])
async def send_help(message: Message):
    response_message = (
        "Привет!\n\n"
        "Я поддерживаю следующие команды:\n"
        "/history - История поиска\n"
        "/start - Начать использование бота\n"
        "/help - Получить справку о доступных командах\n"
        "/moviebd_big_experimental <название файла> - много данных о схожих фильмах и ссылка, чтобы их посмотреть\n, "
        "если ничего не писать, то автоматический будет подставлсять человек паук"
        "/stats - Статистика поиска\n"
        "/pray - :)\n"
        "Просто напиши мне название фильма или сериала, и я постараюсь найти для тебя информацию о нем."
    )
    await message.reply(response_message)


@dp.message_handler(commands=['history'])
async def send_search_history(message: Message):
    async with aiosqlite.connect('bot_db.db') as db:
        cursor = await db.execute(
            "SELECT film_name FROM search_history WHERE user_id = ?",
            (message.from_user.id,)
        )
        rows = await cursor.fetchall()

        if not rows:
            response_message = "История поиска пуста."
        else:
            response_message = "История поиска:\n"
            for row in rows:
                response_message += f"- {row[0]}\n"

        await message.reply(response_message)


async def get_request_to_google_search(name: str, number_results: int = 10) -> tp.Any:
    query = "+".join(name.split()) + f"&num={number_results}"
    async with aiohttp.ClientSession() as session:
        async with session.request("GET", google_url + query, headers=google_headers) as resp:
            response = await resp.text()
            status_code = resp.status
    if status_code >= 400:
        raise RuntimeError
    return json.loads(response)['results']


def get_watch_link(search_results: tp.List[tp.Any]) -> tp.Optional[str]:
    for result in search_results:
        movie_info = result['title'] + ' ' + result['description']
        movie_info = movie_info.lower()
        if ("смотреть" in movie_info and "онлайн" in movie_info) \
                or ("просмотр" in movie_info and "онлайн" in movie_info):
            return result['link']
    return None


async def search_movies_on_themoviedb(api_key, query):
    base_url = "https://api.themoviedb.org/3/search/movie"
    params = {
        'api_key': api_key,
        'query': query
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()

                results = data.get('results', [])
                if not results:
                    return "No results found."

                movies = []
                for result in results:
                    title = result.get('title', 'N/A')
                    release_date = result.get('release_date', 'N/A')
                    overview = result.get('overview', 'No overview available.')
                    movie_id = result.get('id', 'N/A')
                    movie_link = f"https://www.themoviedb.org/movie/{movie_id}"
                    movie_info = (f"Title: {title}\nRelease Date: {release_date}\nOverview: {overview}\nLink:"
                                  f" {movie_link}\n")
                    movies.append(movie_info)
                return movies

    except aiohttp.ClientError as e:
        return f"Error: {e}"


@dp.message_handler(commands=['moviebd_big_experimental'])
async def find_moviebd_big_experimental(message: types.Message):
    if message.text == "/moviebd_big_experimental":
        await message.answer("Вы не ввели ассоциацию фильма")
    else:
        response_message = await search_movies_on_themoviedb(__THEMOVIEDB_TOKEN, '  '.join(message.text.split()[1:]))
        for el in response_message:
            await message.answer(el)
        await message.answer("\n\nThat all connected to the film in the moviedb")


@dp.message_handler()
async def search_film(message: types.Message):
    clean_input = ''.join(
        char for char in message.text.strip().capitalize() if char not in '!@#$%^&*()_-§+=|":/?><~`][,{}№;')
    is_cyrillic = bool(re.search('[а-яА-Я]', clean_input))
    movie_info = await get_movie_info(clean_input, is_cyrillic)
    if not movie_info and is_cyrillic:
        movie_found = await check_movie_existence(clean_input)
        movie_info = await get_movie_info(movie_found["name"], is_cyrillic) if movie_found else None

    if not movie_info:
        response = ("Nothing found"
                    "Try to write exactly the same article of film")
        await message.answer(response)
        return True

    year = movie_info['Year']
    name = movie_info['Name']
    movie_found = await check_movie_existence(name)

    if not movie_found:
        url = 'Не найдена'
    else:
        url = movie_found['url']

    response = (
        f"Name: {name}\n"
        f"Date: {year}\n"
        f"Quality: {movie_info['Rating']}\n"
        f"Description: {movie_info['Description']}\n"
        f"\nLink: {url}\n"
    )

    async with aiosqlite.connect('bot_db.db') as db:
        await db.execute("INSERT INTO search_history (user_id, film_name) VALUES (?, ?)",
                         (message.from_user.id, clean_input))
        await db.commit()

    await message.answer_photo(movie_info['Poster'])
    await message.answer(response)


async def on_startup(_):
    async with aiosqlite.connect('bot_db.db') as db:
        await db.execute("CREATE TABLE IF NOT EXISTS search_history (user_id INTEGER, film_name TEXT)")
        await db.commit()


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
