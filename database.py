# database.py

import sqlite3
from typing import List, Optional, Tuple, Any
from datetime import datetime, date

DB_PATH = "bot.db"


def get_db_connection():
    """Создает подключение к базе данных."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Позволяет обращаться к колонкам по имени
    return conn


def init_db():
    """Инициализирует базу данных и создает таблицы, если их нет."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            registered_at TEXT NOT NULL
        )
    ''')

    # Расписание мастера
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS master_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            is_available INTEGER NOT NULL DEFAULT 1
        )
    ''')

    # Записи клиентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active', 'cancelled', 'completed')),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # Портфолио работ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_file_id TEXT NOT NULL,
            caption TEXT,
            created_at TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()


# === Работа с пользователями ===

def add_user(user_id: int, username: str, full_name: str, phone: str):
    """Добавляет нового пользователя в базу."""
    conn = get_db_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO users (user_id, username, full_name, phone, registered_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, full_name, phone, now)
    )
    conn.commit()
    conn.close()


def get_user(user_id: int) -> Optional[sqlite3.Row]:
    """Возвращает данные пользователя по его Telegram ID."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return user


# === Работа с расписанием ===

def add_schedule_slot(date_str: str, start_time: str, duration_minutes: int):
    """Добавляет новый слот в расписание мастера."""
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO master_schedule (date, start_time, duration_minutes, is_available) VALUES (?, ?, ?, 1)",
        (date_str, start_time, duration_minutes)
    )
    conn.commit()
    conn.close()


def get_available_slots(date_str: str) -> List[sqlite3.Row]:
    """Возвращает список свободных слотов на указанную дату."""
    conn = get_db_connection()
    slots = conn.execute("""
        SELECT ms.id, ms.start_time, ms.duration_minutes
        FROM master_schedule ms
        LEFT JOIN appointments a ON ms.date = a.date AND ms.start_time = a.time AND a.status = 'active'
        WHERE ms.date = ? AND ms.is_available = 1 AND a.id IS NULL
        ORDER BY ms.start_time
    """, (date_str,)).fetchall()
    conn.close()
    return slots


def get_all_slots_by_date(date_str: str) -> List[sqlite3.Row]:
    """Возвращает все слоты (свободные и занятые) на дату — для админки."""
    conn = get_db_connection()
    slots = conn.execute("""
        SELECT ms.id, ms.start_time, ms.duration_minutes, ms.is_available,
               a.user_id, a.status
        FROM master_schedule ms
        LEFT JOIN appointments a ON ms.date = a.date AND ms.start_time = a.time
        WHERE ms.date = ?
        ORDER BY ms.start_time
    """, (date_str,)).fetchall()
    conn.close()
    return slots


def delete_schedule_slot(slot_id: int) -> bool:
    """Удаляет слот из расписания, если на него нет активных записей."""
    conn = get_db_connection()
    # Проверяем наличие активной записи
    active_app = conn.execute("""
        SELECT 1 FROM appointments a
        JOIN master_schedule ms ON a.date = ms.date AND a.time = ms.start_time
        WHERE ms.id = ? AND a.status = 'active'
    """, (slot_id,)).fetchone()

    if active_app:
        conn.close()
        return False  # Нельзя удалить — есть активная запись

    conn.execute("DELETE FROM master_schedule WHERE id = ?", (slot_id,))
    conn.commit()
    conn.close()
    return True


# === Работа с записями ===

def create_appointment(user_id: int, date_str: str, time_str: str) -> int:
    """Создает новую запись и возвращает её ID."""
    conn = get_db_connection()
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO appointments (user_id, date, time, status, created_at) VALUES (?, ?, ?, 'active', ?)",
        (user_id, date_str, time_str, now)
    )
    appointment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return appointment_id


def get_user_appointments(user_id: int, status: str = 'active') -> List[sqlite3.Row]:
    """Возвращает записи пользователя с указанным статусом."""
    conn = get_db_connection()
    if status == 'all':
        apps = conn.execute("""
            SELECT * FROM appointments
            WHERE user_id = ?
            ORDER BY date, time
        """, (user_id,)).fetchall()
    else:
        apps = conn.execute("""
            SELECT * FROM appointments
            WHERE user_id = ? AND status = ?
            ORDER BY date, time
        """, (user_id, status)).fetchall()
    conn.close()
    return apps


def cancel_appointment(appointment_id: int) -> bool:
    """Отменяет запись (меняет статус на 'cancelled')."""
    conn = get_db_connection()
    result = conn.execute(
        "UPDATE appointments SET status = 'cancelled' WHERE id = ? AND status = 'active'",
        (appointment_id,)
    )
    updated = result.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_all_appointments() -> List[sqlite3.Row]:
    """Возвращает все записи для админки."""
    conn = get_db_connection()
    apps = conn.execute("""
        SELECT a.*, u.full_name, u.phone
        FROM appointments a
        JOIN users u ON a.user_id = u.user_id
        ORDER BY a.date DESC, a.time DESC
    """).fetchall()
    conn.close()
    return apps


def update_appointment_status(appointment_id: int, new_status: str) -> bool:
    """Обновляет статус записи (например, на 'cancelled')."""
    if new_status not in ('active', 'cancelled', 'completed'):
        return False
    conn = get_db_connection()
    result = conn.execute(
        "UPDATE appointments SET status = ? WHERE id = ?",
        (new_status, appointment_id)
    )
    success = result.rowcount > 0
    conn.commit()
    conn.close()
    return success


# === Работа с портфолио ===

def add_portfolio_item(photo_file_id: str, caption: str):
    """Добавляет фото в портфолио."""
    conn = get_db_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO portfolio (photo_file_id, caption, created_at) VALUES (?, ?, ?)",
        (photo_file_id, caption, now)
    )
    conn.commit()
    conn.close()


def get_portfolio_items() -> List[sqlite3.Row]:
    """Возвращает все работы из портфолио."""
    conn = get_db_connection()
    items = conn.execute("SELECT * FROM portfolio ORDER BY created_at DESC").fetchall()
    conn.close()
    return items


def delete_portfolio_item(item_id: int) -> bool:
    """Удаляет работу из портфолио."""
    conn = get_db_connection()
    result = conn.execute("DELETE FROM portfolio WHERE id = ?", (item_id,))
    success = result.rowcount > 0
    conn.commit()
    conn.close()
    return success


# === Статистика ===

def get_registered_users_count() -> int:
    """Возвращает общее количество зарегистрированных клиентов."""
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def get_appointments_count_by_days(days: int) -> int:
    """Возвращает количество записей за последние N дней."""
    from datetime import timedelta
    since = (datetime.now().date() - timedelta(days=days)).isoformat()
    conn = get_db_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE date >= ? AND status = 'active'",
        (since,)
    ).fetchone()[0]
    conn.close()
    return count
