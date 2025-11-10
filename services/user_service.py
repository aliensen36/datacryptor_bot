import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

from core.encryption import get_encryptor, DataCategory
from utils.validators import validate_phone, validate_email

from database.engine import session_maker
from database.models import User

logger = logging.getLogger(__name__)


class UserService:
    """
    Сервис для работы с пользователями и их персональными данными
    Обеспечивает автоматическое шифрование/дешифрование данных
    """

    def __init__(self):
        self.encryptor = get_encryptor()
        self.encrypted_fields = [
            'fio', 'phone', 'email', 'address',
            'passport_series', 'passport_number', 'passport_issue_date',
            'passport_issued_by', 'passport_birth_date', 'passport_birth_place',
            'vzh_number', 'vzh_issue_date', 'vzh_expiry_date',
            'patent_number', 'patent_issue_date', 'patent_expiry_date',
            'inn', 'snils', 'driver_license'
        ]

    async def save_user_data(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """
        Сохраняет данные пользователя с автоматическим шифрованием
        """
        try:
            async with session_maker() as session:
                # Проверяем существующего пользователя
                user = await session.get(User, user_id)

                if user:
                    # Обновляем существующего пользователя
                    await self._update_user_data(session, user, user_data)
                else:
                    # Создаем нового пользователя
                    user = await self._create_new_user(session, user_id, user_data)

                await session.commit()
                logger.info(f"User data saved/updated for user_id: {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving user data for {user_id}: {e}")
            return False

    async def _create_new_user(self, session, user_id: int, user_data: Dict[str, Any]) -> User:
        """Создает нового пользователя с зашифрованными данными"""
        encrypted_data = self.encryptor.auto_encrypt_user_data(user_data)

        user = User(
            id=user_id,
            encrypted_data=json.dumps(encrypted_data),
            data_hash=self._create_data_hash(user_data),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_active=True
        )

        session.add(user)
        return user

    async def _update_user_data(self, session, user: User, user_data: Dict[str, Any]):
        """Обновляет данные существующего пользователя"""
        # Дешифровываем текущие данные
        current_data = await self._decrypt_user_data(user)

        # Обновляем данные
        current_data.update(user_data)

        # Шифруем обновленные данные
        encrypted_data = self.encryptor.auto_encrypt_user_data(current_data)

        user.encrypted_data = json.dumps(encrypted_data)
        user.data_hash = self._create_data_hash(current_data)
        user.updated_at = datetime.utcnow()

    async def get_user_data(self, user_id: int) -> Dict[str, Any]:
        """
        Получает и дешифрует данные пользователя
        """
        try:
            async with session_maker() as session:
                user = await session.get(User, user_id)

                if not user or not user.is_active:
                    return {}

                return await self._decrypt_user_data(user)

        except Exception as e:
            logger.error(f"Error getting user data for {user_id}: {e}")
            return {}

    async def _decrypt_user_data(self, user: User) -> Dict[str, Any]:
        """Дешифрует данные пользователя"""
        if not user.encrypted_data:
            return {}

        try:
            encrypted_dict = json.loads(user.encrypted_data)
            return self.encryptor.auto_decrypt_user_data(encrypted_dict)
        except Exception as e:
            logger.error(f"Error decrypting data for user {user.id}: {e}")
            return {}

    async def update_user_field(self, user_id: int, field: str, value: Any) -> bool:
        """
        Обновляет конкретное поле пользователя
        """
        try:
            async with session_maker() as session:
                user = await session.get(User, user_id)

                if not user:
                    return False

                # Получаем текущие данные
                current_data = await self._decrypt_user_data(user)

                # Обновляем поле
                current_data[field] = value

                # Шифруем и сохраняем
                encrypted_data = self.encryptor.auto_encrypt_user_data(current_data)
                user.encrypted_data = json.dumps(encrypted_data)
                user.data_hash = self._create_data_hash(current_data)
                user.updated_at = datetime.utcnow()

                await session.commit()
                logger.info(f"Field '{field}' updated for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating field '{field}' for user {user_id}: {e}")
            return False

    async def delete_user_data(self, user_id: int) -> bool:
        """
        Удаляет все данные пользователя (soft delete)
        """
        try:
            async with session_maker() as session:
                user = await session.get(User, user_id)

                if not user:
                    return False

                # Soft delete - помечаем как неактивного
                user.is_active = False
                user.deleted_at = datetime.utcnow()

                await session.commit()
                logger.info(f"User data deleted for user_id: {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error deleting user data for {user_id}: {e}")
            return False

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Возвращает статистику по данным пользователя
        """
        user_data = await self.get_user_data(user_id)

        if not user_data:
            return {}

        stats = {
            'has_basic_data': bool(user_data.get('fio') and user_data.get('phone')),
            'has_passport': bool(user_data.get('passport_series') and user_data.get('passport_number')),
            'has_vzh': bool(user_data.get('vzh_number')),
            'has_patent': bool(user_data.get('patent_number')),
            'has_inn': bool(user_data.get('inn')),
            'has_snils': bool(user_data.get('snils')),
            'documents_count': 0,
            'last_updated': user_data.get('_encrypted_at', 'неизвестно')
        }

        # Считаем документы
        documents = ['passport', 'vzh', 'patent', 'inn', 'snils']
        stats['documents_count'] = sum(1 for doc in documents if stats[f'has_{doc}'])

        return stats

    async def search_users(self, search_criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Поиск пользователей по критериям (только по незашифрованным полям)
        """
        try:
            async with session_maker() as session:
                query = session.query(User).filter(User.is_active == True)

                # Добавляем критерии поиска
                if 'created_after' in search_criteria:
                    query = query.filter(User.created_at >= search_criteria['created_after'])

                if 'created_before' in search_criteria:
                    query = query.filter(User.created_at <= search_criteria['created_before'])

                users = await session.execute(query)
                users_list = users.scalars().all()

                result = []
                for user in users_list:
                    user_data = await self._decrypt_user_data(user)
                    result.append({
                        'user_id': user.id,
                        'created_at': user.created_at,
                        'has_data': bool(user_data.get('fio'))
                    })

                return result

        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []

    async def export_user_data(self, user_id: int) -> Dict[str, Any]:
        """
        Экспортирует данные пользователя для скачивания
        """
        user_data = await self.get_user_data(user_id)

        if not user_data:
            return {}

        # Убираем служебные поля
        export_data = {k: v for k, v in user_data.items() if not k.startswith('_')}

        return {
            'exported_at': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'data': export_data,
            'format': 'json',
            'compliance': '152-FZ'
        }

    async def validate_user_data(self, user_id: int) -> Dict[str, Any]:
        """
        Валидирует данные пользователя
        """
        user_data = await self.get_user_data(user_id)
        validation_results = {}

        if not user_data:
            return {'valid': False, 'errors': ['Нет данных пользователя']}

        # Валидация ФИО
        if user_data.get('fio'):
            name_parts = user_data['fio'].split()
            if len(name_parts) < 2:
                validation_results['fio'] = 'Неполное ФИО'

        # Валидация телефона
        if user_data.get('phone'):
            if not validate_phone(user_data['phone']):
                validation_results['phone'] = 'Неверный формат телефона'

        # Валидация email
        if user_data.get('email'):
            if not validate_email(user_data['email']):
                validation_results['email'] = 'Неверный формат email'

        # Валидация паспортных данных
        if user_data.get('passport_series') and user_data.get('passport_number'):
            if len(user_data['passport_series']) != 4 or not user_data['passport_series'].isdigit():
                validation_results['passport_series'] = 'Неверная серия паспорта'
            if len(user_data['passport_number']) != 6 or not user_data['passport_number'].isdigit():
                validation_results['passport_number'] = 'Неверный номер паспорта'

        validation_results['valid'] = len(validation_results) == 0
        return validation_results

    async def cleanup_old_data(self, days: int = 365) -> int:
        """
        Очищает данные пользователей, которые не активны больше указанного количества дней
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            async with session_maker() as session:
                result = await session.execute(
                    User.__table__.update()
                    .where(User.updated_at < cutoff_date)
                    .where(User.is_active == True)
                    .values(is_active=False, deleted_at=datetime.utcnow())
                )

                await session.commit()
                deleted_count = result.rowcount

                logger.info(f"Cleaned up {deleted_count} user records older than {days} days")
                return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0

    def _create_data_hash(self, user_data: Dict[str, Any]) -> str:
        """
        Создает хеш данных для отслеживания изменений
        """
        import hashlib

        # Сортируем ключи для консистентности
        sorted_data = json.dumps(user_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(sorted_data.encode('utf-8')).hexdigest()

    async def get_encryption_info(self, user_id: int) -> Dict[str, Any]:
        """
        Возвращает информацию о шифровании данных пользователя
        """
        try:
            async with session_maker() as session:
                user = await session.get(User, user_id)

                if not user:
                    return {}

                encrypted_data = json.loads(user.encrypted_data) if user.encrypted_data else {}

                return {
                    'user_id': user_id,
                    'is_encrypted': '_encrypted' in encrypted_data,
                    'encryption_version': encrypted_data.get('_encryption_version', 'unknown'),
                    'encrypted_at': encrypted_data.get('_encrypted_at', 'unknown'),
                    'fields_encrypted': len([k for k in encrypted_data.keys() if not k.startswith('_')]),
                    'data_hash': user.data_hash
                }

        except Exception as e:
            logger.error(f"Error getting encryption info for user {user_id}: {e}")
            return {}


# Создаем глобальный экземпляр сервиса
user_service = UserService()


# Функции для удобного использования
async def save_user_data(user_id: int, user_data: Dict[str, Any]) -> bool:
    """Сохраняет данные пользователя"""
    return await user_service.save_user_data(user_id, user_data)


async def get_user_data(user_id: int) -> Dict[str, Any]:
    """Получает данные пользователя"""
    return await user_service.get_user_data(user_id)


async def delete_user_data(user_id: int) -> bool:
    """Удаляет данные пользователя"""
    return await user_service.delete_user_data(user_id)


async def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Получает статистику пользователя"""
    return await user_service.get_user_stats(user_id)
