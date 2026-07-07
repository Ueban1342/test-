# bot.py

import os
import sys
from datetime import datetime, timedelta
from typing import List

import telebot
from telebot import types

from config import TELEGRAM_BOT_TOKEN, ADMIN_ID
from database import (
    add_user, get_user, get_available_slots, create_appointment,
    get_user_appointments, cancel_appointment, get_portfolio_items
)
from scheduler import schedule_reminders_for_appointment

# Инициализация бота
if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("❌ Ошибка: Укажите TELEGRAM_BOT_TOKEN в config.py")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# === Вспомогательные функции ===

def send_main_menu(chat_id: int):
    """Отправляет главное меню."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📅 Записаться на маникюр")
    btn2 = types.KeyboardButton("📸 Работы мастера")
    btn3 = types.KeyboardButton("🗓 Мои записи")
    btn4 = types.KeyboardButton("📞 Связаться с мастером")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)


def generate_calendar_buttons(days_ahead: int = 14) -> types.InlineKeyboardMarkup:
    """Генерирует кнопки с датами на ближайшие N дней."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    today = datetime.today().date()
    buttons = []
    for i in range(days_ahead):
        d = today + timedelta(days=i)
        text = d.strftime("%d %b")
        callback_data = f"select_date_{d.isoformat()}"
        buttons.append(types.InlineKeyboardButton(text=text, callback_data=callback_data))
    markup.add(*buttons)
    return markup


def generate_time_buttons(date_str: str) -> types.InlineKeyboardMarkup:
    """Генерирует кнопки со свободными временными слотами на дату."""
    slots = get_available_slots(date_str)
    if not slots:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Нет свободных мест", callback_data="no_slots"))
        return markup

    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for slot in slots:
        time_str = slot['start_time']
        callback_data = f"select_time_{date_str}_{time_str}"
        buttons.append(types.InlineKeyboardButton(time_str, callback_data=callback_data))
    markup.add(*buttons)
    return markup


# === Обработчики команд ===

@bot.message_handler(commands=['start'])
def handle_start(message: types.Message):
    user = get_user(message.from_user.id)
    if user:
        bot.send_message(message.chat.id, f"Рады видеть вас снова, {user['full_name']}!")
        send_main_menu(message.chat.id)
    else:
        bot.send_message(message.chat.id, "Добро пожаловать! Как вас зовут?")
        bot.register_next_step_handler(message, process_name_step)


def process_name_step(message: types.Message):
    full_name = message.text.strip()
    if not full_name:
        bot.send_message(message.chat.id, "Пожалуйста, введите ваше имя.")
        bot.register_next_step_handler(message, process_name_step)
        return

    contact_request = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_button = types.KeyboardButton("📱 Отправить контакт", request_contact=True)
    contact_request.add(contact_button)
    bot.send_message(
        message.chat.id,
        "Теперь отправьте ваш номер телефона:",
        reply_markup=contact_request
    )
    bot.register_next_step_handler(message, process_phone_step, full_name)


def process_phone_step(message: types.Message, full_name: str):
    if message.contact is None:
        bot.send_message(message.chat.id, "Пожалуйста, нажмите кнопку '📱 Отправить контакт'.")
        bot.register_next_step_handler(message, process_phone_step, full_name)
        return

    phone = message.contact.phone_number
    username = message.from_user.username or ""
    add_user(message.from_user.id, username, full_name, phone)
    bot.send_message(
        message.chat.id,
        f"Спасибо, {full_name}! Вы успешно зарегистрированы.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    send_main_menu(message.chat.id)

    # Уведомление мастеру
    try:
        bot.send_message(
            ADMIN_ID,
            f"🆕 Новый клиент зарегистрирован:\n"
            f"Имя: {full_name}\n"
            f"Телефон: {phone}\n"
            f"Telegram: @{username}" if username else f"Telegram ID: {message.from_user.id}"
        )
    except Exception as e:
        print(f"Не удалось уведомить мастера: {e}")


# === Главное меню ===

@bot.message_handler(func=lambda m: m.text == "📅 Записаться на маникюр")
def handle_book_appointment(message: types.Message):
    bot.send_message(
        message.chat.id,
        "Выберите дату записи:",
        reply_markup=generate_calendar_buttons()
    )


@bot.message_handler(func=lambda m: m.text == "📸 Работы мастера")
def handle_portfolio(message: types.Message):
    items = get_portfolio_items()
    if not items:
        bot.send_message(message.chat.id, "Портфолио пока пусто.")
        return

    media_group = []
    for item in items[:10]:  # Telegram ограничивает медиа-группу 10 элементами
        media_group.append(types.InputMediaPhoto(item['photo_file_id'], caption=item['caption']))
    
    try:
        bot.send_media_group(message.chat.id, media_group)
    except Exception as e:
        # Если не удалось отправить группой — отправим по одному
        for item in items[:5]:  # Ограничиваем до 5 фото
            bot.send_photo(message.chat.id, item['photo_file_id'], caption=item['caption'])


@bot.message_handler(func=lambda m: m.text == "🗓 Мои записи")
def handle_my_appointments(message: types.Message):
    apps = get_user_appointments(message.from_user.id, status='active')
    if not apps:
        bot.send_message(message.chat.id, "У вас нет активных записей.")
        return

    for app in apps:
        markup = types.InlineKeyboardMarkup()
        cancel_btn = types.InlineKeyboardButton(
            "❌ Отменить запись",
            callback_data=f"cancel_app_{app['id']}"
        )
        markup.add(cancel_btn)
        bot.send_message(
            message.chat.id,
            f"📅 Дата: {app['date']}\n⏰ Время: {app['time']}\nСтатус: {app['status']}",
            reply_markup=markup
        )


@bot.message_handler(func=lambda m: m.text == "📞 Связаться с мастером")
def handle_contact_master(message: types.Message):
    # Здесь можно отправить контакт или просто текст с номером
    bot.send_message(
        message.chat.id,
        "Вы можете связаться с мастером по телефону: +7 (XXX) XXX-XX-XX\n"
        "Или написать в Telegram: @your_master_username"
    )


# === Callback-обработчики ===

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_date_"))
def handle_date_selection(call: types.CallbackQuery):
    date_str = call.data.replace("select_date_", "")
    bot.edit_message_text(
        "Выберите время:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=generate_time_buttons(date_str)
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("select_time_"))
def handle_time_selection(call: types.CallbackQuery):
    parts = call.data.replace("select_time_", "").split("_", 1)
    if len(parts) != 2:
        bot.answer_callback_query(call.id, "Ошибка выбора времени.", show_alert=True)
        return

    date_str, time_str = parts[0], parts[1]

    # Создаем запись
    appointment_id = create_appointment(call.from_user.id, date_str, time_str)

    # Подтверждение клиенту
    bot.edit_message_text(
        f"✅ Вы успешно записаны!\n📅 Дата: {date_str}\n⏰ Время: {time_str}\n📍 Адрес: ул. Красивая, д. 10",
        call.message.chat.id,
        call.message.message_id
    )

    # Уведомление мастеру
    user = get_user(call.from_user.id)
    try:
        bot.send_message(
            ADMIN_ID,
            f"🔔 Новая запись!\n"
            f"Клиент: {user['full_name']}\n"
            f"Телефон: {user['phone']}\n"
            f"Дата: {date_str}, Время: {time_str}"
        )
    except Exception as e:
        print(f"Не удалось уведомить мастера о записи: {e}")

    # Запланировать напоминания
    schedule_reminders_for_appointment(appointment_id, date_str, time_str, call.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data == "no_slots")
def handle_no_slots(call: types.CallbackQuery):
    bot.answer_callback_query(call.id, "К сожалению, на эту дату нет свободных мест.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_app_"))
def handle_cancel_appointment(call: types.CallbackQuery):
    app_id = int(call.data.replace("cancel_app_", ""))
    success = cancel_appointment(app_id)
    if success:
        bot.edit_message_text(
            "❌ Ваша запись отменена.",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "Запись уже отменена или не найдена.", show_alert=True)


# === Запуск бота ===

if __name__ == "__main__":
    from database import init_db
    init_db()
    print("✅ Бот запущен...")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ Ошибка бота: {e}")
