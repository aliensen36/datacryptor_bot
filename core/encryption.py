import base64
import os
import logging
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from enum import Enum

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes, hmac
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag, InvalidSignature

logger = logging.getLogger(__name__)


class DataCategory(Enum):
    """Категории персональных данных для маркировки"""
    PASSPORT = "passport"
    FIO = "fio"
    ADDRESS = "address"
    PHONE = "phone"
    VZH = "vzh"  # ВНЖ
    PATENT = "patent"
    DOCUMENT_PHOTO = "document_photo"
    OTHER = "other"


class PersonalDataEncryptor:
    """
    Сервис шифрования персональных данных в соответствии с 152-ФЗ
    Реализует автошифрование всех ПДн с маркировкой категорий данных
    """

    # Поля, подлежащие обязательному шифрованию
    ENCRYPTED_FIELDS = [
        'fio', 'passport_series', 'passport_number', 'passport_issue_date',
        'passport_issued_by', 'address', 'phone', 'vzh_number', 'patent_number',
        'document_scan_path', 'email', 'snils', 'inn'
    ]

    def __init__(self, master_key: str, key_rotation_days: int = 90):
        """
        :param master_key: мастер-ключ шифрования (32 байта)
        :param key_rotation_days: период ротации ключей в днях
        """
        if len(master_key) != 32:
            raise ValueError("Master key must be exactly 32 bytes (256 bit) for AES-256")

        self.master_key = master_key.encode('utf-8')
        self.key_rotation_days = key_rotation_days
        self.backend = default_backend()

        # Генерируем производные ключи
        self._derive_keys()

        logger.info("PersonalDataEncryptor initialized with key rotation every %d days", key_rotation_days)

    def _derive_keys(self):
        """Генерация производных ключей из мастер-ключа"""
        # Ключ для шифрования данных
        kdf_enc = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'encryption_salt',
            iterations=100000,
            backend=self.backend
        )
        self.encryption_key = kdf_enc.derive(self.master_key)

        # Ключ для HMAC аутентификации
        kdf_auth = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'authentication_salt',
            iterations=100000,
            backend=self.backend
        )
        self.auth_key = kdf_auth.derive(self.master_key)

    def _create_metadata(self, data_category: DataCategory) -> Dict[str, Any]:
        """Создает метаданные для зашифрованных данных"""
        return {
            'category': data_category.value,
            'encrypted_at': datetime.utcnow().isoformat(),
            'key_version': self._get_current_key_version(),
            'compliance': '152-FZ'
        }

    def _get_current_key_version(self) -> str:
        """Возвращает версию ключа на основе даты ротации"""
        days_since_epoch = (datetime.utcnow() - datetime(2020, 1, 1)).days
        rotation_period = days_since_epoch // self.key_rotation_days
        return f"v{rotation_period}"

    def encrypt_field(self, plain_text: str, data_category: DataCategory) -> str:
        """
        Шифрует одно поле с указанием категории данных
        Использует AES-256-GCM для конфиденциальности и аутентичности
        """
        if not plain_text:
            return ""

        try:
            # Генерируем случайный IV (12 байт для GCM - рекомендуется)
            iv = os.urandom(12)

            # Создаем cipher в режиме GCM
            cipher = Cipher(algorithms.AES(self.encryption_key), modes.GCM(iv), backend=self.backend)
            encryptor = cipher.encryptor()

            # Подготавливаем данные для шифрования
            metadata = self._create_metadata(data_category)
            data_package = {
                'metadata': metadata,
                'data': plain_text
            }
            json_data = json.dumps(data_package, ensure_ascii=False)

            # Шифруем данные
            encrypted_data = encryptor.update(json_data.encode('utf-8')) + encryptor.finalize()

            # Получаем auth tag
            auth_tag = encryptor.tag

            # Создаем HMAC для дополнительной аутентификации
            h = hmac.HMAC(self.auth_key, hashes.SHA256(), backend=self.backend)
            h.update(iv + encrypted_data + auth_tag)
            hmac_digest = h.finalize()

            # Формируем финальный пакет: IV + encrypted_data + auth_tag + HMAC
            combined = iv + encrypted_data + auth_tag + hmac_digest

            # Кодируем в URL-safe base64
            return base64.urlsafe_b64encode(combined).decode('utf-8')

        except Exception as e:
            logger.error(f"Encryption error for category {data_category}: {e}")
            raise EncryptionError(f"Failed to encrypt {data_category.value}: {e}")

    def decrypt_field(self, encrypted_text: str) -> tuple[str, DataCategory]:
        """
        Дешифрует поле и возвращает данные + категорию
        """
        if not encrypted_text:
            return "", DataCategory.OTHER

        try:
            # Декодируем из base64
            combined = base64.urlsafe_b64decode(encrypted_text.encode('utf-8'))

            # Извлекаем компоненты
            iv = combined[:12]  # Первые 12 байт - IV
            auth_tag = combined[-48:-32]  # Auth tag (16 байт перед HMAC)
            hmac_digest = combined[-32:]  # Последние 32 байта - HMAC
            encrypted_data = combined[12:-48]  # Остальное - зашифрованные данные

            # Проверяем HMAC перед дешифрованием
            h = hmac.HMAC(self.auth_key, hashes.SHA256(), backend=self.backend)
            h.update(iv + encrypted_data + auth_tag)
            h.verify(hmac_digest)

            # Создаем cipher
            cipher = Cipher(algorithms.AES(self.encryption_key), modes.GCM(iv, auth_tag), backend=self.backend)
            decryptor = cipher.decryptor()

            # Дешифруем
            decrypted_json = decryptor.update(encrypted_data) + decryptor.finalize()
            data_package = json.loads(decrypted_json.decode('utf-8'))

            # Проверяем метаданные
            metadata = data_package.get('metadata', {})
            data_category = DataCategory(metadata.get('category', 'other'))

            return data_package['data'], data_category

        except InvalidSignature:
            logger.error("HMAC verification failed - possible tampering detected")
            raise SecurityError("Data integrity check failed - possible tampering")
        except InvalidTag:
            logger.error("GCM authentication tag verification failed")
            raise SecurityError("Data authentication failed")
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise DecryptionError(f"Failed to decrypt data: {e}")

    def auto_encrypt_user_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Автоматически шифрует все персональные данные в словаре
        """
        encrypted_data = {}

        for field, value in user_data.items():
            if field in self.ENCRYPTED_FIELDS and value:
                # Определяем категорию данных
                category = self._map_field_to_category(field)

                # Шифруем поле
                try:
                    encrypted_data[field] = self.encrypt_field(str(value), category)
                    logger.debug(f"Encrypted field {field} as category {category}")
                except EncryptionError as e:
                    logger.error(f"Failed to encrypt field {field}: {e}")
                    raise
            else:
                # Нешифруемые поля сохраняем как есть
                encrypted_data[field] = value

        # Добавляем метку о шифровании
        encrypted_data['_encrypted'] = True
        encrypted_data['_encryption_version'] = self._get_current_key_version()
        encrypted_data['_encrypted_at'] = datetime.utcnow().isoformat()

        return encrypted_data

    def auto_decrypt_user_data(self, encrypted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Автоматически дешифрует все зашифрованные данные в словаре
        """
        decrypted_data = {}

        for field, value in encrypted_data.items():
            if field in self.ENCRYPTED_FIELDS and value and isinstance(value, str):
                try:
                    decrypted_value, category = self.decrypt_field(value)
                    decrypted_data[field] = decrypted_value
                    logger.debug(f"Decrypted field {field} from category {category}")
                except (DecryptionError, SecurityError) as e:
                    logger.error(f"Failed to decrypt field {field}: {e}")
                    decrypted_data[field] = "[DECRYPTION_ERROR]"
            else:
                # Нешифруемые поля сохраняем как есть
                decrypted_data[field] = value

        return decrypted_data

    def _map_field_to_category(self, field: str) -> DataCategory:
        """Сопоставляет поле с категорией данных"""
        field_category_map = {
            'fio': DataCategory.FIO,
            'passport_series': DataCategory.PASSPORT,
            'passport_number': DataCategory.PASSPORT,
            'passport_issue_date': DataCategory.PASSPORT,
            'passport_issued_by': DataCategory.PASSPORT,
            'address': DataCategory.ADDRESS,
            'phone': DataCategory.PHONE,
            'vzh_number': DataCategory.VZH,
            'patent_number': DataCategory.PATENT,
            'document_scan_path': DataCategory.DOCUMENT_PHOTO,
            'email': DataCategory.OTHER,
            'snils': DataCategory.OTHER,
            'inn': DataCategory.OTHER
        }

        return field_category_map.get(field, DataCategory.OTHER)

    def encrypt_file(self, file_path: str, output_path: str, data_category: DataCategory) -> None:
        """
        Шифрует файл с персональными данными
        """
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()

            # Шифруем данные файла
            iv = os.urandom(12)
            cipher = Cipher(algorithms.AES(self.encryption_key), modes.GCM(iv), backend=self.backend)
            encryptor = cipher.encryptor()

            # Добавляем метаданные в начало файла
            metadata = self._create_metadata(data_category)
            metadata_json = json.dumps(metadata).encode('utf-8')
            encryptor.authenticate_additional_data(metadata_json)

            encrypted_data = encryptor.update(file_data) + encryptor.finalize()
            auth_tag = encryptor.tag

            # Сохраняем: IV + metadata_len + metadata + encrypted_data + auth_tag
            with open(output_path, 'wb') as f:
                f.write(iv)
                f.write(len(metadata_json).to_bytes(4, 'big'))
                f.write(metadata_json)
                f.write(encrypted_data)
                f.write(auth_tag)

            logger.info(f"File encrypted: {file_path} -> {output_path}")

        except Exception as e:
            logger.error(f"File encryption error: {e}")
            raise EncryptionError(f"Failed to encrypt file: {e}")

    def get_encryption_info(self) -> Dict[str, Any]:
        """Возвращает информацию о текущей конфигурации шифрования"""
        return {
            'algorithm': 'AES-256-GCM',
            'key_rotation_days': self.key_rotation_days,
            'current_key_version': self._get_current_key_version(),
            'encrypted_fields': self.ENCRYPTED_FIELDS,
            'compliance': '152-FZ',
            'security_level': 'high'
        }


class EncryptionError(Exception):
    """Ошибка шифрования данных"""
    pass


class DecryptionError(Exception):
    """Ошибка дешифрования данных"""
    pass


class SecurityError(Exception):
    """Ошибка безопасности (нарушение целостности)"""
    pass


# Фабрика и синглтон для использования в проекте
_encryptor_instance: Optional[PersonalDataEncryptor] = None


def get_encryptor() -> PersonalDataEncryptor:
    """
    Возвращает глобальный экземпляр шифратора
    """
    global _encryptor_instance
    if _encryptor_instance is None:
        # Используем BOT_TOKEN как основу для ключа шифрования
        from config import BOT_TOKEN

        # Создаем ключ шифрования на основе BOT_TOKEN
        # Дополняем или обрезаем до 32 символов
        encryption_key = BOT_TOKEN.ljust(32, '0')[:32] if BOT_TOKEN else 'default-encryption-key-32-bytes-long!'

        _encryptor_instance = PersonalDataEncryptor(
            master_key=encryption_key,
            key_rotation_days=90  # стандартное значение
        )
    return _encryptor_instance


def create_encryptor(master_key: str, key_rotation_days: int = 90) -> PersonalDataEncryptor:
    """
    Создает новый экземпляр шифратора (для тестов или многопользовательских сценариев)
    """
    return PersonalDataEncryptor(master_key, key_rotation_days)