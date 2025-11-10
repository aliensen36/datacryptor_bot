from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)  # Telegram user ID
    encrypted_data = Column(Text)  # Зашифрованные данные в JSON
    data_hash = Column(String(64))  # Хеш данных для отслеживания изменений
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)


class UserDocument(Base):
    __tablename__ = 'user_documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    document_type = Column(String(50), nullable=False)  # passport, vzh, patent, etc.
    encrypted_file_path = Column(String(500))  # Путь к зашифрованному файлу
    original_filename = Column(String(255))
    file_size = Column(Integer)
    created_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
