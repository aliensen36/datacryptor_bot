import sqlite3
import logging
from typing import Optional, Dict, Any


class Database:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Таблица для пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица для персональных данных
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_personal_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        phone TEXT,
                        full_name TEXT,
                        passport_data TEXT,
                        address TEXT,
                        additional_docs TEXT,
                        encrypted_data BLOB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')

                conn.commit()
                logging.info("Database initialized successfully")

        except Exception as e:
            logging.error(f"Error initializing database: {e}")

    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Добавление пользователя в базу"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Error adding user: {e}")
            return False

    def save_personal_data(self, user_id: int, personal_data: Dict[str, Any]):
        """Сохранение персональных данных пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Проверяем, есть ли уже запись
                cursor.execute('SELECT id FROM user_personal_data WHERE user_id = ?', (user_id,))
                existing = cursor.fetchone()

                if existing:
                    # Обновляем существующую запись
                    cursor.execute('''
                        UPDATE user_personal_data 
                        SET phone = ?, full_name = ?, passport_data = ?, address = ?, additional_docs = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (
                        personal_data.get('phone'),
                        personal_data.get('full_name'),
                        personal_data.get('passport'),
                        personal_data.get('address'),
                        personal_data.get('additional_docs'),
                        user_id
                    ))
                else:
                    # Создаем новую запись
                    cursor.execute('''
                        INSERT INTO user_personal_data (user_id, phone, full_name, passport_data, address, additional_docs)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        user_id,
                        personal_data.get('phone'),
                        personal_data.get('full_name'),
                        personal_data.get('passport'),
                        personal_data.get('address'),
                        personal_data.get('additional_docs')
                    ))

                conn.commit()
                return True

        except Exception as e:
            logging.error(f"Error saving personal data: {e}")
            return False

    def get_user_data(self, user_id: int) -> Optional[Dict]:
        """Получение данных пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT u.user_id, u.username, u.first_name, u.last_name,
                           pd.phone, pd.full_name, pd.passport_data, pd.address, pd.additional_docs
                    FROM users u
                    LEFT JOIN user_personal_data pd ON u.user_id = pd.user_id
                    WHERE u.user_id = ?
                ''', (user_id,))

                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None

        except Exception as e:
            logging.error(f"Error getting user data: {e}")
            return None

    def user_has_data(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя сохраненные данные"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM user_personal_data WHERE user_id = ?', (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Error checking user data: {e}")
            return False
