"""
Сервис для генерации отчеств и склонения фамилий на разных языках Евразии.
"""


def generate_patronymic(father_first_name: str, child_gender: str, culture: str = "ru") -> str | None:
    """
    Генерирует отчество на основе имени отца, пола ребенка и культуры.
    """
    if not father_first_name:
        return None

    name = father_first_name.strip()

    if culture in ["ru", "uk", "be"]:
        return _generate_slavic_patronymic(name, child_gender, culture)
    elif culture == "pl":
        return _generate_polish_patronymic(name, child_gender)
    elif culture in ["kk", "ky", "uz"]:
        return _generate_turkic_patronymic(name, child_gender, culture)
    elif culture == "az":
        return _generate_azerbaijani_patronymic(name, child_gender)
    elif culture in ["sv", "no", "da"]:
        return _generate_scandinavian_patronymic(name, child_gender, culture)
    elif culture == "is":
        return _generate_icelandic_patronymic(name, child_gender)
    else:
        return _generate_slavic_patronymic(name, child_gender, "ru")


def _generate_slavic_patronymic(name: str, gender: str, culture: str = "ru") -> str | None:
    """Генерация отчества для славянских языков."""
    name_lower = name.lower()
    last_letter = name_lower[-1]

    full_exceptions = {
        ("лев", "male"): "львович",
        ("лев", "female"): "львовна",
        ("павел", "male"): "павлович",
        ("павел", "female"): "павловна",
        ("пётр", "male"): "петрович",
        ("пётр", "female"): "петровна",
        ("илья", "male"): "ильич",
        ("илья", "female"): "ильинична",
        ("никита", "male"): "никитич",
        ("никита", "female"): "никитична",
        ("лука", "male"): "лукич",
        ("лука", "female"): "лукична",
        ("фома", "male"): "фомич",
        ("фома", "female"): "фомична",
    }

    exception_key = (name_lower, gender)
    if exception_key in full_exceptions:
        return full_exceptions[exception_key].capitalize()

    base = name_lower
    if base.endswith("ь"):
        base = base[:-1]

    if culture == "uk":
        if gender == "male":
            if last_letter == "й":
                result = base[:-1] + "ійович"
            elif last_letter in ["а", "я"]:
                result = base[:-1] + "ич"
            else:
                result = base + "ович"
        else:
            if last_letter == "й":
                result = base[:-1] + "ійвна"
            elif last_letter in ["а", "я"]:
                result = base[:-1] + "івна"
            else:
                result = base + "вна"
    else:
        if gender == "male":
            if last_letter == "й":
                result = base[:-1] + "евич"
            elif last_letter in ["а", "я"]:
                result = base[:-1] + "ич"
            else:
                result = base + "ович"
        else:
            if last_letter == "й":
                result = base[:-1] + "евна"
            elif last_letter in ["а", "я"]:
                result = base[:-1] + "ична"
            else:
                result = base + "овна"

    return result.capitalize()


def _generate_polish_patronymic(name: str, gender: str) -> str | None:
    """Генерация отчества для польского языка."""
    name_lower = name.lower()
    if name_lower.endswith("a"):
        base = name_lower[:-1]
    else:
        base = name_lower

    if gender == "male":
        result = (base + "wicz") if base.endswith("e") else (base + "owicz")
    else:
        result = (base + "wna") if base.endswith("e") else (base + "ówna")
    return result.capitalize()


def _generate_turkic_patronymic(name: str, gender: str, culture: str) -> str | None:
    """Генерация отчества для тюркских языков."""
    name_lower = name.lower()
    if culture == "kk":
        result = name_lower + ("ұлы" if gender == "male" else "қызы")
    elif culture == "ky":
        result = name_lower + ("уулу" if gender == "male" else "кызы")
    else:
        result = name_lower + (" o'g'li" if gender == "male" else " qizi")
    return result


def _generate_azerbaijani_patronymic(name: str, gender: str) -> str | None:
    """Генерация отчества для азербайджанского языка."""
    name_lower = name.lower()
    return name_lower + ("oğlu" if gender == "male" else "qızı")


def _generate_scandinavian_patronymic(name: str, gender: str, culture: str) -> str | None:
    """Генерация отчества для скандинавских языков."""
    name_lower = name.lower()
    if culture == "sv":
        result = name_lower + ("son" if gender == "male" else "dotter")
    elif culture in ["no", "da"]:
        result = name_lower + ("sen" if gender == "male" else "datter")
    else:
        return None
    return result


def _generate_icelandic_patronymic(name: str, gender: str) -> str | None:
    """Генерация отчества для исландского языка."""
    name_lower = name.lower()
    return name_lower + ("son" if gender == "male" else "dóttir")


# === СКЛОНЕНИЕ ФАМИЛИЙ ===


def decline_lastname(lastname: str, gender: str, culture: str = "ru") -> str | None:
    """
    Склоняет фамилию по полу для славянских языков.

    Правила для русского языка:
    - -ов → -ова (Иванов → Иванова)
    - -ев → -ева (Сергеев → Сергеева)
    - -ин → -ина (Путин → Путина)
    - -ский → -ская (Достоевский → Достоевская)
    - -ой → -ая (Толстой → Толстая)
    - -ий → -ая (Долгий → Долгая)

    Для женских фамилий, уже оканчивающихся на -а/-я, склонение не применяется.

    Returns:
        Склонённая фамилия или None, если входные данные пустые.
    """
    # Возвращаем None для пустых входных данных
    if not lastname or not gender:
        return None

    if culture not in ["ru", "uk", "be"]:
        # Для других культур пока не склоняем
        return lastname

    # Если пол мужской — возвращаем как есть
    if gender == "male":
        return lastname

    # Женский пол — склоняем
    name_lower = lastname.lower().strip()

    # Уже женская форма (оканчивается на -а/-я, но не -ова/-ева/-ева)
    if name_lower.endswith(("ова", "ева", "ина", "ая", "яя", "ская")):
        return lastname

    # Русские/славянские окончания
    if name_lower.endswith("ов") or name_lower.endswith("ёв") or name_lower.endswith("ев") or name_lower.endswith("ин"):
        return lastname + "а"
    elif (
        name_lower.endswith("ский")
        or name_lower.endswith("ский")
        or name_lower.endswith("ской")
        or name_lower.endswith("ой")
        or name_lower.endswith("ий")
        or name_lower.endswith("ый")
    ):
        return lastname[:-2] + "ая"

    # Фамилии на -ко, -енко, -ич не склоняются
    if name_lower.endswith(("ко", "енко", "ич", "ых", "их")):
        return lastname

    # По умолчанию не склоняем
    return lastname
