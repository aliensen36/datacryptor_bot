import re
from datetime import datetime


def validate_phone(phone: str) -> bool:
    """Валидация номера телефона"""
    # Убираем все нецифровые символы
    clean_phone = re.sub(r'\D', '', phone)

    # Проверяем российские форматы: 7XXXXXXXXXX, 8XXXXXXXXXX, XXXXXXXXXX
    if len(clean_phone) == 10 and clean_phone.startswith('9'):
        return True
    elif len(clean_phone) == 11 and (clean_phone.startswith('7') or clean_phone.startswith('8')):
        return True

    return False


def validate_email(email: str) -> bool:
    """Валидация email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_passport_series(series: str) -> bool:
    """Валидация серии паспорта"""
    return len(series) == 4 and series.isdigit()


def validate_passport_number(number: str) -> bool:
    """Валидация номера паспорта"""
    return len(number) == 6 and number.isdigit()


def validate_inn(inn: str) -> bool:
    """Валидация ИНН"""
    clean_inn = re.sub(r'\D', '', inn)
    return len(clean_inn) in [10, 12] and clean_inn.isdigit()


def validate_snils(snils: str) -> bool:
    """Валидация СНИЛС"""
    clean_snils = re.sub(r'\D', '', snils)
    return len(clean_snils) == 11 and clean_snils.isdigit()


def validate_date(date_str: str) -> bool:
    """Валидация даты в формате ДД.ММ.ГГГГ"""
    try:
        datetime.strptime(date_str, '%d.%m.%Y')
        return True
    except ValueError:
        return False
