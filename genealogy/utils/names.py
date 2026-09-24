"""
Сервис для генерации отчеств на разных языках Евразии.
"""


def generate_patronymic(father_first_name: str, child_gender: str, culture: str = "ru") -> str | None:
    """
    Генерирует отчество на основе имени отца, пола ребенка и культуры.

    Поддерживаемые культуры:
    - ru: русский
    - uk: украинский
    - be: белорусский
    - pl: польский
    - kk: казахский
    - ky: кыргызский
    - uz: узбекский
    - az: азербайджанский
    - sv: шведский
    - no: норвежский
    - da: датский
    - is: исландский
    """
    if not father_first_name:
        return None

    name = father_first_name.strip()

    # Маршрутизация по культуре
    if culture in ["ru", "uk", "be"]:  # Славянские
        return _generate_slavic_patronymic(name, child_gender, culture)
    elif culture == "pl":  # Польский
        return _generate_polish_patronymic(name, child_gender)
    elif culture in ["kk", "ky", "uz"]:  # Тюркские
        return _generate_turkic_patronymic(name, child_gender, culture)
    elif culture == "az":  # Азербайджанский
        return _generate_azerbaijani_patronymic(name, child_gender)
    elif culture in ["sv", "no", "da"]:  # Скандинавские
        return _generate_scandinavian_patronymic(name, child_gender, culture)
    elif culture == "is":  # Исландский
        return _generate_icelandic_patronymic(name, child_gender)
    else:
        # По умолчанию используем русскую логику
        return _generate_slavic_patronymic(name, child_gender, "ru")


def _generate_slavic_patronymic(name: str, gender: str, culture: str = "ru") -> str | None:
    """Генерация отчества для славянских языков."""
    name_lower = name.lower()
    last_letter = name_lower[-1]

    # Словарь полных форм для исключений (имя, пол) → отчество
    # Для имён с нестандартным склонением храним готовые формы
    full_exceptions = {
        ('лев', 'male'): 'львович',
        ('лев', 'female'): 'львовна',
        ('павел', 'male'): 'павлович',
        ('павел', 'female'): 'павловна',
        ('пётр', 'male'): 'петрович',
        ('пётр', 'female'): 'петровна',
        ('илья', 'male'): 'ильич',
        ('илья', 'female'): 'ильинична',
        ('никита', 'male'): 'никитич',
        ('никита', 'female'): 'никитична',
        ('лука', 'male'): 'лукич',
        ('лука', 'female'): 'лукична',
        ('фома', 'male'): 'фомич',
        ('фома', 'female'): 'фомична',
    }

    # Если имя в исключениях — возвращаем готовую форму
    exception_key = (name_lower, gender)
    if exception_key in full_exceptions:
        return full_exceptions[exception_key].capitalize()

    # Для имён не из исключений — применяем обычные правила
    base = name_lower
    if base.endswith('ь'):
        base = base[:-1]

    if culture == "uk":  # Украинский
        if gender == 'male':
            if last_letter == 'й':
                result = base[:-1] + 'ійович'
            elif last_letter in ['а', 'я']:
                result = base[:-1] + 'ич'
            else:
                result = base + 'ович'
        else:  # female
            if last_letter == 'й':
                result = base[:-1] + 'ійвна'
            elif last_letter in ['а', 'я']:
                result = base[:-1] + 'івна'
            else:
                result = base + 'вна'
    else:  # Русский и белорусский
        if gender == 'male':
            if last_letter == 'й':
                result = base[:-1] + 'евич'
            elif last_letter in ['а', 'я']:
                result = base[:-1] + 'ич'
            else:
                result = base + 'ович'
        else:  # female
            if last_letter == 'й':
                result = base[:-1] + 'евна'
            elif last_letter in ['а', 'я']:
                result = base[:-1] + 'ична'
            else:
                result = base + 'овна'

    return result.capitalize()


def _generate_polish_patronymic(name: str, gender: str) -> str | None:
    """Генерация отчества для польского языка."""
    name_lower = name.lower()

    if name_lower.endswith('a'):
        base = name_lower[:-1]
    else:
        base = name_lower

    if gender == 'male':
        if base.endswith('e'):
            result = base + 'wicz'
        else:
            result = base + 'owicz'
    else:  # female
        if base.endswith('e'):
            result = base + 'wna'
        else:
            result = base + 'ówna'

    return result.capitalize()


def _generate_turkic_patronymic(name: str, gender: str, culture: str) -> str | None:
    """
    Генерация отчества для тюркских языков.

    Внимание: тюркские патронимические суффиксы пишутся со строчной буквы.
    """
    name_lower = name.lower()

    if culture == "kk":  # Казахский
        if gender == 'male':
            result = name_lower + 'ұлы'
        else:
            result = name_lower + 'қызы'
    elif culture == "ky":  # Кыргызский
        if gender == 'male':
            result = name_lower + 'уулу'
        else:
            result = name_lower + 'кызы'
    else:  # Узбекский и другие
        if gender == 'male':
            result = name_lower + " o'g'li"
        else:
            result = name_lower + ' qizi'

    # БЕЗ .capitalize() — тюркские патронимы пишутся со строчной буквы
    return result


def _generate_azerbaijani_patronymic(name: str, gender: str) -> str | None:
    """
    Генерация отчества для азербайджанского языка.

    Внимание: азербайджанские патронимические суффиксы пишутся со строчной буквы.
    """
    name_lower = name.lower()

    if gender == 'male':
        result = name_lower + 'oğlu'
    else:
        result = name_lower + 'qızı'

    # БЕЗ .capitalize() — азербайджанские патронимы пишутся со строчной буквы
    return result


def _generate_scandinavian_patronymic(name: str, gender: str, culture: str) -> str | None:
    """
    Генерация отчества для скандинавских языков.

    Внимание: скандинавские патронимические суффиксы пишутся со строчной буквы.
    """
    name_lower = name.lower()

    if culture == "sv":  # Шведский
        if gender == 'male':
            result = name_lower + 'son'
        else:
            result = name_lower + 'dotter'
    elif culture in ["no", "da"]:  # Норвежский/датский
        if gender == 'male':
            result = name_lower + 'sen'
        else:
            result = name_lower + 'datter'
    else:
        return None

    # БЕЗ .capitalize() — скандинавские патронимы пишутся со строчной буквы
    return result


def _generate_icelandic_patronymic(name: str, gender: str) -> str | None:
    """
    Генерация отчества для исландского языка.

    Внимание: исландские патронимические суффиксы пишутся со строчной буквы.
    """
    name_lower = name.lower()

    if gender == 'male':
        result = name_lower + 'son'
    else:
        result = name_lower + 'dóttir'

    # БЕЗ .capitalize() — исландские патронимы пишутся со строчной буквы
    return result