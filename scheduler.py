# scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import pytz
from config import TIMEZONE, REMINDER_24H, REMINDER_2H
from database import get_user_appointments
import telebot
from config import TELEGRAM_BOT_TOKEN
from typing import Optional

# Инициализируем бота для отправки сообщений из планировщика
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
timezone = pytz.timezone(TIMEZONE)
scheduler = BackgroundScheduler(timezone=timezone)
scheduler.start()


def send_reminder(user_id: int, date_str: str, time_str: str, hours_before: int):
    """Отправляет напоминание клиенту."""
    try:
        bot.send_message(
            user_id,
            f"🔔 Напоминаем!\n"
            f"Через {hours_before} ч. у вас запись на маникюр.\n"
            f"📅 Дата: {date_str}\n⏰ Время: {time_str}\n📍 Адрес: ул. Красивая, д. 10"
        )
    except Exception as e:
        print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")


def schedule_reminders_for_appointment(appointment_id: int, date_str: str, time_str: str, user_id: int):
    """Планирует напоминания за 24ч и за 2ч до записи."""
    # Парсим дату и время записи
    dt_str = f"{date_str} {time_str}"
    appointment_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    appointment_dt = timezone.localize(appointment_dt)

    # Напоминание за 24 часа
    reminder_24h = appointment_dt - timedelta(hours=REMINDER_24H)
    if reminder_24h > datetime.now(timezone):
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=reminder_24h),
            args=[user_id, date_str, time_str, REMINDER_24H]
        )

    # Напоминание за 2 часа
    reminder_2h = appointment_dt - timedelta(hours=REMINDER_2H)
    if reminder_2h > datetime.now(timezone):
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=reminder_2h),
            args=[user_id, date_str, time_str, REMINDER_2H]
        )

    print(f"✅ Напоминания запланированы для записи {appointment_id}")
