import asyncio
import logging
import os
import traceback
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import aiosqlite

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Путь к базе данных
DB_PATH = "/app/reputation.db"


async def init_db():
    """Инициализация базы данных"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reputation (
                    user_id INTEGER,
                    chat_id INTEGER,
                    username TEXT,
                    rep INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    voter_id INTEGER,
                    target_id INTEGER,
                    chat_id INTEGER,
                    vote_type TEXT,
                    vote_date DATE,
                    PRIMARY KEY (voter_id, target_id, chat_id, vote_date)
                )
            """)
            
            await db.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Database init error: {e}")
        logging.error(traceback.format_exc())


async def get_rep(user_id: int, chat_id: int) -> int:
    """Получение репутации пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT rep FROM reputation WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0
    except Exception as e:
        logging.error(f"get_rep error: {e}")
        return 0


async def change_rep(voter_id: int, target_id: int, chat_id: int, 
                     vote_type: str, username: str = None) -> str:
    """Изменение репутации пользователя"""
    try:
        today = datetime.now().date()
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT * FROM votes 
                   WHERE voter_id = ? AND target_id = ? AND chat_id = ? AND vote_date = ?""",
                (voter_id, target_id, chat_id, today)
            ) as cursor:
                existing_vote = await cursor.fetchone()
                
                if existing_vote:
                    return "Error: You have already voted for this user today."
            
            await db.execute(
                "INSERT INTO votes (voter_id, target_id, chat_id, vote_type, vote_date) VALUES (?, ?, ?, ?, ?)",
                (voter_id, target_id, chat_id, vote_type, today)
            )
            
            await db.execute(
                """INSERT INTO reputation (user_id, chat_id, username, rep) 
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, chat_id) 
                   DO UPDATE SET rep = rep + ?, username = COALESCE(?, username)""",
                (target_id, chat_id, username, 1 if vote_type == '+' else -1,
                 1 if vote_type == '+' else -1, username)
            )
            
            await db.commit()
            
            new_rep = await get_rep(target_id, chat_id)
            logging.info(f"Rep changed: voter={voter_id}, target={target_id}, type={vote_type}, new_rep={new_rep}")
            return f"Reputation updated. Current reputation: {new_rep}"
    except Exception as e:
        logging.error(f"change_rep error: {e}")
        logging.error(traceback.format_exc())
        return "Error: Something went wrong. Try again later."


async def get_top_rep(chat_id: int, limit: int = 20) -> tuple:
    """Получение топ-20 положительной и отрицательной репутации"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT username, rep FROM reputation 
                   WHERE chat_id = ? AND rep > 0 
                   ORDER BY rep DESC LIMIT ?""",
                (chat_id, limit)
            ) as cursor:
                top_positive = await cursor.fetchall()
            
            async with db.execute(
                """SELECT username, rep FROM reputation 
                   WHERE chat_id = ? AND rep < 0 
                   ORDER BY rep ASC LIMIT ?""",
                (chat_id, limit)
            ) as cursor:
                top_negative = await cursor.fetchall()
                
            return top_positive, top_negative
    except Exception as e:
        logging.error(f"get_top_rep error: {e}")
        return [], []


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.reply(
        "Reputation Bot\n\n"
        "Commands:\n"
        "+rep @username - Increase reputation\n"
        "-rep @username - Decrease reputation\n"
        "/mr - Your reputation\n"
        "/cr - Reputation leaderboard\n\n"
        "Rules: You can vote for each user once per day."
    )


@dp.message_handler(commands=['mr'])
async def cmd_my_rep(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username or message.from_user.full_name
    
    rep = await get_rep(user_id, chat_id)
    await message.reply(f"User: {username}\nReputation: {rep}")


@dp.message_handler(commands=['cr'])
async def cmd_top_rep(message: types.Message):
    chat_id = message.chat.id
    
    top_positive, top_negative = await get_top_rep(chat_id)
    
    response = "Reputation Leaderboard\n"
    response += "=" * 30 + "\n\n"
    
    response += "Top 20 Positive:\n"
    response += "-" * 20 + "\n"
    if top_positive:
        for i, (username, rep) in enumerate(top_positive, 1):
            name = username or "Unknown"
            response += f"{i}. {name}: +{rep}\n"
    else:
        response += "No data yet.\n"
    
    response += "\nTop 20 Negative:\n"
    response += "-" * 20 + "\n"
    if top_negative:
        for i, (username, rep) in enumerate(top_negative, 1):
            name = username or "Unknown"
            response += f"{i}. {name}: {rep}\n"
    else:
        response += "No data yet.\n"
    
    await message.reply(response)


@dp.message_handler(content_types=['text'])
async def handle_all_text(message: types.Message):
    """Обработчик всех текстовых сообщений"""
    if not message.text:
        return
    
    text = message.text.strip().lower()
    
    # Проверяем только точные совпадения +rep или -rep
    if text not in ['+rep', '-rep', '+реп', '-реп']:
        return
    
    logging.info(f"Vote attempt: user={message.from_user.id}, text={text}, reply={message.reply_to_message is not None}")
    
    voter_id = message.from_user.id
    chat_id = message.chat.id
    
    if '+rep' in text or '+реп' in text:
        vote_type = '+'
    else:
        vote_type = '-'
    
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Error: Reply to a user's message with +rep or -rep.")
        return
    
    target_id = message.reply_to_message.from_user.id
    target_username = (message.reply_to_message.from_user.username or 
                      message.reply_to_message.from_user.full_name)
    
    if voter_id == target_id:
        await message.reply("Error: Cannot vote for yourself.")
        return
    
    result = await change_rep(voter_id, target_id, chat_id, vote_type, target_username)
    await message.reply(result)


async def on_startup(dp):
    await init_db()
    logging.info("Bot started successfully")


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
