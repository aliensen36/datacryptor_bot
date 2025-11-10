import logging
from typing import Dict, Any

from aiogram import F, types, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.encryption import get_encryptor
from services.user_service import UserService
from services.file_processor import FileProcessor
from utils.validators import (
    validate_phone,
    validate_passport_series,
    validate_passport_number,
    validate_date,
    validate_inn,
    validate_snils
)

logger = logging.getLogger(__name__)

start_router = Router()


class PersonalDataStates(StatesGroup):
    waiting_for_fio = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_passport_series = State()
    waiting_for_passport_number = State()
    waiting_for_passport_issue_date = State()
    waiting_for_passport_issued_by = State()
    waiting_for_inn = State()
    waiting_for_snils = State()


# Инициализация сервисов
encryptor = get_encryptor()
user_service = UserService()
file_processor = FileProcessor()


# ===== ОСНОВНЫЕ ХЕНДЛЕРЫ =====

@start_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    logger.info(f"User {user_id} started personal data collection")

    # Проверяем существующие данные
    existing_data = await user_service.get_user_data(user_id)
    if existing_data and existing_data.get('fio'):
        await handle_existing_user(message, existing_data)
        return

    # Новый пользователь
    welcome_text = (
        "👋 <b>Добро пожаловать в сервис сбора персональных данных!</b>\n\n"
        "Мы собираем и безопасно храним ваши данные в соответствии с <b>152-ФЗ</b>\n\n"
        "🔒 <b>Гарантии безопасности:</b>\n"
        "• Все данные шифруются перед сохранением\n"
        "• Доступ к данным только по secure-ключу\n"
        "• Файлы проверяются антивирусом\n\n"
        "Начнем с основных данных. Введите ваше <b>ФИО полностью</b>:\n"
        "<code>Иванов Иван Иванович</code>"
    )

    await message.answer(welcome_text)
    await state.set_state(PersonalDataStates.waiting_for_fio)


@start_router.message(PersonalDataStates.waiting_for_fio)
async def process_fio(message: types.Message, state: FSMContext):
    """Обработка ФИО"""
    fio = message.text.strip()

    # Валидация ФИО
    name_parts = fio.split()
    if len(name_parts) < 2:
        await message.answer(
            "❌ <b>Неверный формат ФИО</b>\n\n"
            "Пожалуйста, введите ФИО полностью:\n"
            "<code>Иванов Иван Иванович</code>"
        )
        return

    await state.update_data(fio=fio)
    await message.answer(
        f"✅ <b>ФИО сохранено:</b> {fio}\n\n"
        "Теперь введите ваш <b>номер телефона</b>:\n"
        "<code>+79991234567</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_phone)


@start_router.message(PersonalDataStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    """Обработка телефона"""
    phone = message.text.strip()

    if not validate_phone(phone):
        await message.answer(
            "❌ <b>Неверный формат телефона</b>\n\n"
            "Пожалуйста, введите номер:\n"
            "<code>+79991234567</code>"
        )
        return

    # Нормализуем номер
    clean_phone = ''.join(filter(str.isdigit, phone))
    if len(clean_phone) == 10:
        clean_phone = '7' + clean_phone

    formatted_phone = f"+7{clean_phone[1:4]} {clean_phone[4:7]}-{clean_phone[7:9]}-{clean_phone[9:]}"

    await state.update_data(phone=formatted_phone, phone_raw=clean_phone)
    await message.answer(
        f"✅ <b>Телефон сохранен:</b> {formatted_phone}\n\n"
        "Теперь введите ваш <b>адрес проживания</b>:\n"
        "<code>г. Москва, ул. Примерная, д. 1, кв. 1</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_address)


@start_router.message(PersonalDataStates.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    """Обработка адреса"""
    address = message.text.strip()

    if len(address) < 10:
        await message.answer(
            "❌ <b>Слишком короткий адрес</b>\n\n"
            "Пожалуйста, введите полный адрес:"
        )
        return

    await state.update_data(address=address)

    # Предлагаем выбор: паспорт или другие документы
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📘 Паспорт РФ",
                    callback_data="collect_passport"
                ),
                types.InlineKeyboardButton(
                    text="💳 ИНН/СНИЛС",
                    callback_data="collect_inn_snils"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="✅ Завершить основные данные",
                    callback_data="finish_basic_data"
                )
            ]
        ]
    )

    await message.answer(
        f"✅ <b>Адрес сохранен:</b> {address}\n\n"
        "Какие документы хотите добавить?",
        reply_markup=keyboard
    )


# ===== ПАСПОРТНЫЕ ДАННЫЕ =====

@start_router.callback_query(F.data == "collect_passport")
async def start_passport_collection(callback: types.CallbackQuery, state: FSMContext):
    """Начало сбора паспортных данных"""
    await callback.message.answer(
        "📘 <b>Сбор паспортных данных</b>\n\n"
        "Введите <b>серию паспорта</b> (4 цифры):\n"
        "<code>1234</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_passport_series)
    await callback.answer()


@start_router.message(PersonalDataStates.waiting_for_passport_series)
async def process_passport_series(message: types.Message, state: FSMContext):
    """Обработка серии паспорта"""
    series = message.text.strip()

    if not validate_passport_series(series):
        await message.answer(
            "❌ <b>Неверная серия паспорта</b>\n\n"
            "Серия должна состоять из 4 цифр:\n"
            "<code>1234</code>"
        )
        return

    await state.update_data(passport_series=series)
    await message.answer(
        f"✅ <b>Серия сохранена:</b> {series}\n\n"
        "Введите <b>номер паспорта</b> (6 цифр):\n"
        "<code>567890</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_passport_number)


@start_router.message(PersonalDataStates.waiting_for_passport_number)
async def process_passport_number(message: types.Message, state: FSMContext):
    """Обработка номера паспорта"""
    number = message.text.strip()

    if not validate_passport_number(number):
        await message.answer(
            "❌ <b>Неверный номер паспорта</b>\n\n"
            "Номер должен состоять из 6 цифр:\n"
            "<code>567890</code>"
        )
        return

    await state.update_data(passport_number=number)
    await message.answer(
        f"✅ <b>Номер сохранен:</b> {number}\n\n"
        "Введите <b>дату выдачи</b> (ДД.ММ.ГГГГ):\n"
        "<code>01.01.2020</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_passport_issue_date)


@start_router.message(PersonalDataStates.waiting_for_passport_issue_date)
async def process_passport_issue_date(message: types.Message, state: FSMContext):
    """Обработка даты выдачи паспорта"""
    date_str = message.text.strip()

    if not validate_date(date_str):
        await message.answer(
            "❌ <b>Неверный формат даты</b>\n\n"
            "Введите дату в формате ДД.ММ.ГГГГ:\n"
            "<code>01.01.2020</code>"
        )
        return

    await state.update_data(passport_issue_date=date_str)
    await message.answer(
        f"✅ <b>Дата выдачи сохранена:</b> {date_str}\n\n"
        "Введите <b>кем выдан паспорт</b>:\n"
        "<code>ОУФМС России по г. Москве</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_passport_issued_by)


@start_router.message(PersonalDataStates.waiting_for_passport_issued_by)
async def process_passport_issued_by(message: types.Message, state: FSMContext):
    """Обработка органа выдачи"""
    issued_by = message.text.strip()

    if len(issued_by) < 5:
        await message.answer("❌ Слишком короткое название. Введите полное название органа:")
        return

    await state.update_data(passport_issued_by=issued_by)
    await message.answer(
        f"✅ <b>Орган выдачи сохранен:</b> {issued_by}\n\n"
        "📘 <b>Паспортные данные собраны!</b>"
    )

    # Возвращаем к выбору действий
    await offer_additional_actions(message, state)


# ===== ДОПОЛНИТЕЛЬНЫЕ ДОКУМЕНТЫ =====

@start_router.callback_query(F.data == "collect_inn_snils")
async def start_inn_snils_collection(callback: types.CallbackQuery, state: FSMContext):
    """Начало сбора ИНН/СНИЛС"""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="💳 ИНН", callback_data="collect_inn"),
                types.InlineKeyboardButton(text="📋 СНИЛС", callback_data="collect_snils")
            ]
        ]
    )

    await callback.message.answer(
        "Выберите документ для добавления:",
        reply_markup=keyboard
    )
    await callback.answer()


@start_router.callback_query(F.data == "collect_inn")
async def collect_inn_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для ИНН"""
    await callback.message.answer(
        "💳 <b>Ввод ИНН</b>\n\n"
        "Введите ваш <b>ИНН</b> (12 цифр):\n"
        "<code>123456789012</code>"
    )
    await state.set_state(PersonalDataStates.waiting_for_inn)
    await callback.answer()


@start_router.message(PersonalDataStates.waiting_for_inn)
async def process_inn(message: types.Message, state: FSMContext):
    """Обработка ИНН"""
    inn = message.text.strip()

    if not validate_inn(inn):
        await message.answer(
            "❌ <b>Неверный ИНН</b>\n\n"
            "ИНН должен состоять из 12 цифр. Попробуйте снова:"
        )
        return

    await state.update_data(inn=inn)
    await message.answer(f"✅ <b>ИНН сохранен:</b> {inn}")
    await offer_additional_actions(message, state)


@start_router.message(PersonalDataStates.waiting_for_snils)
async def process_snils(message: types.Message, state: FSMContext):
    """Обработка СНИЛС"""
    snils = message.text.strip()

    if not validate_snils(snils):
        await message.answer(
            "❌ <b>Неверный СНИЛС</b>\n\n"
            "СНИЛС должен состоять из 11 цифр. Попробуйте снова:"
        )
        return

    await state.update_data(snils=snils)
    await message.answer(f"✅ <b>СНИЛС сохранен:</b> {snils}")
    await offer_additional_actions(message, state)


# ===== ЗАВЕРШЕНИЕ =====

@start_router.callback_query(F.data == "finish_basic_data")
async def finish_data_handler(callback: types.CallbackQuery, state: FSMContext):
    """Завершение сбора данных"""
    await finish_data_collection(callback.message, state)
    await callback.answer()


async def finish_data_collection(message: types.Message, state: FSMContext):
    """Финальное сохранение данных"""
    user_id = message.from_user.id

    try:
        user_data = await state.get_data()
        await user_service.save_user_data(user_id, user_data)
        await state.clear()

        await show_final_summary(message, user_data)
        logger.info(f"User {user_id} completed data collection")

    except Exception as e:
        logger.error(f"Error saving data for user {user_id}: {e}")
        await message.answer("❌ Ошибка при сохранении данных")


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def handle_existing_user(message: types.Message, existing_data: Dict[str, Any]):
    """Обработка пользователя с существующими данными"""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔄 Обновить данные", callback_data="update_data"),
                types.InlineKeyboardButton(text="📋 Мои данные", callback_data="show_my_data")
            ]
        ]
    )

    fio = existing_data.get('fio', 'не указано')
    await message.answer(
        f"👤 <b>С возвращением, {fio.split()[0]}!</b>\n\n"
        "У вас уже есть сохраненные данные.",
        reply_markup=keyboard
    )


async def offer_additional_actions(message: types.Message, state: FSMContext):
    """Предложение дополнительных действий"""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📘 Паспорт", callback_data="collect_passport"),
                types.InlineKeyboardButton(text="💳 ИНН", callback_data="collect_inn")
            ],
            [
                types.InlineKeyboardButton(text="📋 СНИЛС", callback_data="collect_snils"),
                types.InlineKeyboardButton(text="✅ Завершить", callback_data="finish_basic_data")
            ]
        ]
    )

    await message.answer(
        "📑 <b>Дополнительные документы</b>\n\n"
        "Вы можете добавить другие документы или завершить ввод:",
        reply_markup=keyboard
    )


async def show_final_summary(message: types.Message, user_data: Dict[str, Any]):
    """Показ итогового сообщения"""
    fio = user_data.get('fio', 'не указано')

    documents = []
    if user_data.get('passport_series'):
        documents.append("📘 Паспорт")
    if user_data.get('inn'):
        documents.append("💳 ИНН")
    if user_data.get('snils'):
        documents.append("📋 СНИЛС")

    docs_text = "\n".join(documents) if documents else "• Основные данные"

    summary = (
        f"🎉 <b>Данные сохранены, {fio.split()[0]}!</b>\n\n"
        f"<b>Собраны:</b>\n"
        f"• 👤 {fio}\n"
        f"• 📞 {user_data.get('phone', 'не указан')}\n"
        f"<b>Документы:</b>\n{docs_text}\n\n"
        "🔒 <i>Все данные зашифрованы</i>\n\n"
        "<b>Команды:</b>\n"
        "/my_data - посмотреть данные\n"
        "/update - обновить\n"
        "/delete - удалить"
    )

    await message.answer(summary)
