import logging
from typing import Dict, Any

from aiogram import F, types, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.encryption import get_encryptor
from services.user_service import UserService
from services.file_processor import FileProcessor
from utils.validators import validate_phone, validate_passport_series, validate_passport_number

logger = logging.getLogger(__name__)

# Роутер для хендлеров персональных данных
personal_data_router = Router()


class PersonalDataStates(StatesGroup):
    """Состояния для сбора персональных данных"""
    waiting_for_fio = State()
    waiting_for_passport_series = State()
    waiting_for_passport_number = State()
    waiting_for_passport_issue_date = State()
    waiting_for_passport_issued_by = State()
    waiting_for_address = State()
    waiting_for_phone = State()
    waiting_for_document_photo = State()
    waiting_for_vzh_data = State()
    waiting_for_patent_data = State()


class PersonalDataHandler:
    """Обработчик персональных данных с автошифрованием"""

    def __init__(self):
        self.encryptor = get_encryptor()
        self.user_service = UserService()
        self.file_processor = FileProcessor()

    async def start_data_collection(self, message: types.Message, state: FSMContext):
        """Начало сбора персональных данных"""
        user_id = message.from_user.id

        # Проверяем, есть ли уже данные у пользователя
        existing_data = await self.user_service.get_user_data(user_id)
        if existing_data and existing_data.get('fio'):
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="🔄 Обновить данные",
                            callback_data="update_existing_data"
                        ),
                        types.InlineKeyboardButton(
                            text="📋 Показать текущие",
                            callback_data="show_existing_data"
                        )
                    ]
                ]
            )
            await message.answer(
                "ℹ️ У вас уже есть сохраненные данные. Хотите обновить их или посмотреть текущие?",
                reply_markup=keyboard
            )
            return

        await message.answer(
            "👋 <b>Сбор персональных данных</b>\n\n"
            "Мы обеспечиваем безопасное хранение ваших данных с помощью шифрования "
            "в соответствии с 152-ФЗ о защите персональных данных.\n\n"
            "🔒 <i>Все данные шифруются перед сохранением и недоступны без ключа</i>\n\n"
            "Для начала введите ваше <b>ФИО полностью</b> (Фамилия Имя Отчество):"
        )
        await state.set_state(PersonalDataStates.waiting_for_fio)

    async def process_fio(self, message: types.Message, state: FSMContext):
        """Обработка ФИО"""
        fio = message.text.strip()

        # Валидация ФИО
        if len(fio.split()) < 2:
            await message.answer(
                "❌ <b>Неверный формат ФИО</b>\n\n"
                "Пожалуйста, введите ФИО полностью через пробел:\n"
                "<code>Иванов Иван Иванович</code>"
            )
            return

        if len(fio) > 150:
            await message.answer(
                "❌ <b>Слишком длинное ФИО</b>\n\n"
                "Пожалуйста, введите ФИО не более 150 символов:"
            )
            return

        # Сохраняем в состояние
        await state.update_data(fio=fio)

        await message.answer(
            "✅ <b>ФИО сохранено</b>\n\n"
            "Теперь введите <b>серию паспорта</b> (4 цифры):\n"
            "<code>1234</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_passport_series)

    async def process_passport_series(self, message: types.Message, state: FSMContext):
        """Обработка серии паспорта"""
        series = message.text.strip()

        if not validate_passport_series(series):
            await message.answer(
                "❌ <b>Неверная серия паспорта</b>\n\n"
                "Серия должна состоять из <b>4 цифр</b>. Попробуйте еще раз:\n"
                "<code>1234</code>"
            )
            return

        await state.update_data(passport_series=series)

        await message.answer(
            "✅ <b>Серия паспорта сохранена</b>\n\n"
            "Теперь введите <b>номер паспорта</b> (6 цифр):\n"
            "<code>567890</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_passport_number)

    async def process_passport_number(self, message: types.Message, state: FSMContext):
        """Обработка номера паспорта"""
        number = message.text.strip()

        if not validate_passport_number(number):
            await message.answer(
                "❌ <b>Неверный номер паспорта</b>\n\n"
                "Номер должен состоять из <b>6 цифр</b>. Попробуйте еще раз:\n"
                "<code>567890</code>"
            )
            return

        await state.update_data(passport_number=number)

        await message.answer(
            "✅ <b>Номер паспорта сохранен</b>\n\n"
            "Теперь введите <b>дату выдачи паспорта</b> в формате ДД.ММ.ГГГГ:\n"
            "<code>01.01.2020</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_passport_issue_date)

    async def process_passport_issue_date(self, message: types.Message, state: FSMContext):
        """Обработка даты выдачи паспорта"""
        date_str = message.text.strip()

        try:
            from datetime import datetime
            issue_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            if issue_date > datetime.now().date():
                await message.answer(
                    "❌ <b>Дата выдачи не может быть в будущем</b>\n\n"
                    "Пожалуйста, введите корректную дату в формате ДД.ММ.ГГГГ:"
                )
                return
        except ValueError:
            await message.answer(
                "❌ <b>Неверный формат даты</b>\n\n"
                "Пожалуйста, введите дату в формате <b>ДД.ММ.ГГГГ</b>:\n"
                "<code>01.01.2020</code>"
            )
            return

        await state.update_data(passport_issue_date=date_str)

        await message.answer(
            "✅ <b>Дата выдачи сохранена</b>\n\n"
            "Теперь введите <b>кем выдан паспорт</b>:\n"
            "<code>ОУФМС России по г. Москве</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_passport_issued_by)

    async def process_passport_issued_by(self, message: types.Message, state: FSMContext):
        """Обработка органа выдачи паспорта"""
        issued_by = message.text.strip()

        if len(issued_by) < 5:
            await message.answer(
                "❌ <b>Слишком короткое название органа выдачи</b>\n\n"
                "Пожалуйста, введите полное название:"
            )
            return

        await state.update_data(passport_issued_by=issued_by)

        await message.answer(
            "✅ <b>Орган выдачи сохранен</b>\n\n"
            "Теперь введите ваш <b>адрес проживания</b>:\n"
            "<code>г. Москва, ул. Примерная, д. 1, кв. 1</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_address)

    async def process_address(self, message: types.Message, state: FSMContext):
        """Обработка адреса"""
        address = message.text.strip()

        if len(address) < 10:
            await message.answer(
                "❌ <b>Слишком короткий адрес</b>\n\n"
                "Пожалуйста, введите полный адрес проживания:"
            )
            return

        await state.update_data(address=address)

        await message.answer(
            "✅ <b>Адрес сохранен</b>\n\n"
            "Теперь введите ваш <b>номер телефона</b>:\n"
            "<code>+79991234567</code> или <code>89991234567</code>"
        )
        await state.set_state(PersonalDataStates.waiting_for_phone)

    async def process_phone(self, message: types.Message, state: FSMContext):
        """Обработка телефона"""
        phone = message.text.strip()

        if not validate_phone(phone):
            await message.answer(
                "❌ <b>Неверный формат телефона</b>\n\n"
                "Пожалуйста, введите номер в формате:\n"
                "<code>+79991234567</code> или <code>89991234567</code>"
            )
            return

        await state.update_data(phone=phone)

        # Предлагаем дополнительные документы или завершаем
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="📷 Загрузить фото паспорта",
                        callback_data="upload_passport_photo"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="📝 ВНЖ данные",
                        callback_data="add_vzh_data"
                    ),
                    types.InlineKeyboardButton(
                        text="📄 Патент данные",
                        callback_data="add_patent_data"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="✅ Завершить ввод",
                        callback_data="finish_data_input"
                    )
                ]
            ]
        )

        await message.answer(
            "✅ <b>Телефон сохранен</b>\n\n"
            "Основные данные собраны! Вы можете:\n"
            "• 📷 Загрузить фото паспорта\n"
            "• 📝 Добавить данные ВНЖ\n"
            "• 📄 Добавить данные патента\n"
            "• ✅ Завершить ввод данных\n\n"
            "<i>Все данные будут автоматически зашифрованы</i>",
            reply_markup=keyboard
        )
        await state.set_state(PersonalDataStates.waiting_for_document_photo)

    async def process_document_photo(self, message: types.Message, state: FSMContext):
        """Обработка фото документа"""
        user_id = message.from_user.id

        if not message.photo:
            await message.answer(
                "❌ Пожалуйста, отправьте фото документа"
            )
            return

        try:
            # Берем фото наивысшего качества
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)

            # Обрабатываем файл (проверка антивирусом + шифрование)
            file_path = await self.file_processor.process_uploaded_file(
                file_info, user_id, 'passport_photo'
            )

            # Сохраняем путь к зашифрованному файлу
            await state.update_data(document_scan_path=file_path)

            await message.answer(
                "✅ <b>Фото документа успешно сохранено и зашифровано!</b>\n\n"
                "Файл проверен антивирусом и защищен шифрованием."
            )

        except Exception as e:
            logger.error(f"Error processing document photo for user {user_id}: {e}")
            await message.answer(
                "❌ <b>Ошибка при обработке фото</b>\n\n"
                "Пожалуйста, попробуйте отправить фото еще раз."
            )

    async def finish_data_collection(self, message: types.Message, state: FSMContext):
        """Завершение сбора данных и сохранение в БД"""
        user_id = message.from_user.id

        try:
            # Получаем все данные из состояния
            user_data = await state.get_data()

            # Автошифрование и сохранение данных
            await self.user_service.save_user_data(user_id, user_data)

            # Очищаем состояние
            await state.clear()

            # Показываем подтверждение
            await self.show_data_saved_message(message, user_data)

            logger.info(f"User {user_id} successfully saved encrypted personal data")

        except Exception as e:
            logger.error(f"Error saving user data for {user_id}: {e}")
            await message.answer(
                "❌ <b>Ошибка при сохранении данных</b>\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )

    async def show_data_saved_message(self, message: types.Message, user_data: Dict[str, Any]):
        """Показывает сообщение об успешном сохранении данных"""
        # Показываем только часть данных для безопасности
        fio = user_data.get('fio', '')
        passport_series = user_data.get('passport_series', '')
        passport_number = user_data.get('passport_number', '')

        masked_passport = ""
        if passport_series and passport_number:
            masked_passport = f"{passport_series[:2]}** {passport_number[:2]}****"

        message_text = (
            "🎉 <b>Данные успешно сохранены!</b>\n\n"
            f"<b>ФИО:</b> {fio}\n"
            f"<b>Паспорт:</b> {masked_passport}\n"
            f"<b>Телефон:</b> {user_data.get('phone', '')[:4]}***\n\n"
            "🔒 <i>Все данные зашифрованы и защищены в соответствии с 152-ФЗ</i>\n\n"
            "<b>Доступные команды:</b>\n"
            "/my_data - посмотреть данные\n"
            "/update - обновить данные\n"
            "/delete - удалить данные"
        )

        await message.answer(message_text)

    async def show_user_data(self, message: types.Message):
        """Показывает данные пользователя (с маскировкой конфиденциальных данных)"""
        user_id = message.from_user.id

        try:
            user_data = await self.user_service.get_user_data(user_id)

            if not user_data or not user_data.get('fio'):
                await message.answer(
                    "ℹ️ <b>У вас нет сохраненных данных</b>\n\n"
                    "Используйте /start для начала ввода данных."
                )
                return

            # Маскируем конфиденциальные данные для показа
            masked_data = self._mask_sensitive_data(user_data)

            response = (
                "📋 <b>Ваши сохраненные данные:</b>\n\n"
                f"<b>ФИО:</b> {masked_data['fio']}\n"
                f"<b>Паспорт:</b> {masked_data['passport']}\n"
                f"<b>Дата выдачи:</b> {masked_data.get('passport_issue_date', 'не указано')}\n"
                f"<b>Кем выдан:</b> {masked_data.get('passport_issued_by', 'не указано')}\n"
                f"<b>Адрес:</b> {masked_data.get('address', 'не указано')}\n"
                f"<b>Телефон:</b> {masked_data.get('phone', 'не указано')}\n\n"
                "🔒 <i>Данные хранятся в зашифрованном виде</i>"
            )

            await message.answer(response)

        except Exception as e:
            logger.error(f"Error showing data for user {user_id}: {e}")
            await message.answer(
                "❌ <b>Ошибка при получении данных</b>\n\n"
                "Пожалуйста, попробуйте позже."
            )

    def _mask_sensitive_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Маскирует конфиденциальные данные для показа пользователю"""
        masked = user_data.copy()

        # Маскируем паспорт
        if masked.get('passport_series') and masked.get('passport_number'):
            series = masked['passport_series']
            number = masked['passport_number']
            masked['passport'] = f"{series[:2]}** {number[:2]}****"
        else:
            masked['passport'] = "не указано"

        # Маскируем телефон
        if masked.get('phone'):
            phone = masked['phone']
            if len(phone) > 4:
                masked['phone'] = f"{phone[:4]}***"

        # Не показываем полные sensitive данные даже себе
        masked.pop('passport_series', None)
        masked.pop('passport_number', None)

        return masked

    async def delete_user_data(self, message: types.Message):
        """Удаление данных пользователя"""
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✅ Да, удалить все данные",
                        callback_data="confirm_delete_all"
                    ),
                    types.InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="cancel_delete"
                    )
                ]
            ]
        )

        await message.answer(
            "⚠️ <b>Внимание! Удаление всех персональных данных</b>\n\n"
            "Это действие:\n"
            "• Безвозвратно удалит все ваши данные\n"
            "• Включая паспортные данные, фото документов\n"
            "• Не может быть отменено\n\n"
            "<b>Вы уверены, что хотите продолжить?</b>",
            reply_markup=keyboard
        )


# Создаем экземпляр обработчика
handler = PersonalDataHandler()


# Регистрируем хендлеры
@personal_data_router.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await handler.start_data_collection(message, state)


@personal_data_router.message(Command("my_data"))
async def my_data_handler(message: types.Message):
    await handler.show_user_data(message)


@personal_data_router.message(Command("delete"))
async def delete_handler(message: types.Message):
    await handler.delete_user_data(message)


@personal_data_router.message(PersonalDataStates.waiting_for_fio)
async def fio_handler(message: types.Message, state: FSMContext):
    await handler.process_fio(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_passport_series)
async def passport_series_handler(message: types.Message, state: FSMContext):
    await handler.process_passport_series(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_passport_number)
async def passport_number_handler(message: types.Message, state: FSMContext):
    await handler.process_passport_number(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_passport_issue_date)
async def passport_issue_date_handler(message: types.Message, state: FSMContext):
    await handler.process_passport_issue_date(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_passport_issued_by)
async def passport_issued_by_handler(message: types.Message, state: FSMContext):
    await handler.process_passport_issued_by(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_address)
async def address_handler(message: types.Message, state: FSMContext):
    await handler.process_address(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_phone)
async def phone_handler(message: types.Message, state: FSMContext):
    await handler.process_phone(message, state)


@personal_data_router.message(PersonalDataStates.waiting_for_document_photo, F.photo)
async def document_photo_handler(message: types.Message, state: FSMContext):
    await handler.process_document_photo(message, state)


# Callback handlers для инлайн кнопок
@personal_data_router.callback_query(F.data == "finish_data_input")
async def finish_data_callback(callback: types.CallbackQuery, state: FSMContext):
    await handler.finish_data_collection(callback.message, state)
    await callback.answer()


@personal_data_router.callback_query(F.data == "upload_passport_photo")
async def upload_photo_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📷 <b>Загрузка фото паспорта</b>\n\n"
        "Пожалуйста, отправьте фото страницы паспорта с вашими данными.\n"
        "Фото будет проверено антивирусом и зашифровано."
    )
    await callback.answer()
