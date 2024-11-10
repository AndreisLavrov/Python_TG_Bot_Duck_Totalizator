import telebot
import psycopg2
import random

# Настройки бота и базы данных
BOT_TOKEN = 'YOUR-BOT-TOKEN'
DATABASE_URL = 'postgresql://duckdb_owner:pTIMBNFSRn24@ep-rough-night-a2cto3uw.eu-central-1.aws.neon.tech/duckdb?sslmode=require'

# Создание экземпляра бота
bot = telebot.TeleBot(BOT_TOKEN)

# --- Функции работы с базой данных ---
def connect_to_db():
    return psycopg2.connect(DATABASE_URL)

def create_tables():
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS race (
                race_id SERIAL PRIMARY KEY,
                active BOOLEAN DEFAULT TRUE,
                num_ducks INTEGER  -- Новый столбец для количества уток
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    bet_id SERIAL PRIMARY KEY,
                    race_id INTEGER REFERENCES race(race_id) ON DELETE CASCADE,
                    user_id INTEGER,
                    duck_number INTEGER,
                    UNIQUE (race_id, user_id),
                    UNIQUE (race_id, duck_number)
                );
            """)
            conn.commit()

def start_new_race(num_ducks):
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO race (active, num_ducks) VALUES (TRUE, %s) RETURNING race_id",
                (num_ducks,),  
            )
            race_id = cur.fetchone()[0]
            conn.commit()
            return race_id

def get_active_race_id():
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT race_id FROM race WHERE active = TRUE LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None

def finish_race(race_id):
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE race SET active = FALSE WHERE race_id = %s", (race_id,))
            conn.commit()

def place_bet(race_id, user_id, duck_number):
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO bets (race_id, user_id, duck_number) VALUES (%s, %s, %s)",
                    (race_id, user_id, duck_number),
                )
                conn.commit()
                return True
            except psycopg2.errors.UniqueViolation:
                return False

def get_bets_for_race(race_id):
    with connect_to_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, duck_number FROM bets WHERE race_id = %s", (race_id,))
            return {row[0]: row[1] for row in cur.fetchall()}


# --- Обработчики команд ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Это бот для утиного тотализатора. Используйте команды:\n"
        "/ducks <количество> - установить количество уточек\n"
        "/bet <номер уточки> - сделать ставку\n"
        "/results <номер уточки> - объявить результаты",
    )

@bot.message_handler(commands=["ducks"])
def handle_ducks(message):
    try:
        num_ducks = int(message.text.split()[1])
        if num_ducks > 1:
            race_id = start_new_race(num_ducks)  
            bot.send_message(
                message.chat.id,
                f"Забег #{race_id} с {num_ducks} утками готов! Делайте ваши ставки с помощью /bet <номер уточки>.",
            )
        else:
            bot.reply_to(message, "Количество уточек должно быть больше 1.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте команду /ducks <количество уточек>.")

@bot.message_handler(commands=['bet'])
def handle_bet(message):
    race_id = get_active_race_id()
    if not race_id:
        bot.reply_to(message, "Забег еще не начался! Дождитесь команды /ducks.")
        return

    try:
        duck_number = int(message.text.split()[1])

        # Получаем num_ducks из базы данных
        with connect_to_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT num_ducks FROM race WHERE race_id = %s", (race_id,)
                )
                num_ducks = cur.fetchone()[0]

        if 1 <= duck_number <= num_ducks:
            user_id = message.from_user.id
            if place_bet(race_id, user_id, duck_number):
                bot.reply_to(message, f"Вы поставили на уточку номер {duck_number}!")
            else:
                bot.reply_to(message, f"Уточка номер {duck_number} уже занята! Выберите другую.")
        else:
            bot.reply_to(message, f"Неверный номер уточки. Выберите от 1 до {num_ducks}.")
    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте команду /bet <номер уточки>.")

@bot.message_handler(commands=["results"])
def handle_results(message):
    race_id = get_active_race_id()
    if not race_id:
        bot.reply_to(message, "Забег еще не начался!")
        return

    try:
        winning_duck = int(message.text.split()[1])

        # Получаем num_ducks из базы данных
        with connect_to_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT num_ducks FROM race WHERE race_id = %s", (race_id,)
                )
                num_ducks = cur.fetchone()[0]

        if not 1 <= winning_duck <= num_ducks:
            bot.reply_to(
                message, f"Неверный номер уточки. Выберите от 1 до {num_ducks}."
            )
            return

        bets = get_bets_for_race(race_id)
        winners = [user_id for user_id, duck in bets.items() if duck == winning_duck]

        if winners:
            winner_mentions = [
                f"<a href='tg://user?id={user_id}'>Уточка номер {winning_duck} победила!</a>"
                for user_id in winners
            ]
            bot.send_message(
                message.chat.id, ", ".join(winner_mentions), parse_mode="HTML"
            )
        else:
            bot.send_message(
                message.chat.id,
                f"Уточка номер {winning_duck} победила! К сожалению, никто не сделал на нее ставку.",
            )

        finish_race(race_id)

    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте команду /results <номер уточки>.")


# Создание таблиц при запуске
create_tables()

# Запуск бота
bot.polling(none_stop=True)