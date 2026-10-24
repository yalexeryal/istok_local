"""
Утилита для парсинга GEDCOM-файлов.
Не зависит от внешних библиотек — читает файл напрямую.
"""

import re


def parse_date(gedcom_date: str) -> str | None:
    """Преобразует дату из формата GEDCOM в YYYY-MM-DD."""
    if not gedcom_date:
        return None

    clean_date = gedcom_date.strip()

    # Убираем маркеры приближённости
    for prefix in ["~", "ABT ", "BEF ", "AFT ", "CAL ", "EST "]:
        if clean_date.upper().startswith(prefix):
            clean_date = clean_date[len(prefix) :].strip()
            break

    month_map = {
        "JAN": "01",
        "FEB": "02",
        "MAR": "03",
        "APR": "04",
        "MAY": "05",
        "JUN": "06",
        "JUL": "07",
        "AUG": "08",
        "SEP": "09",
        "OCT": "10",
        "NOV": "11",
        "DEC": "12",
    }

    # DD MMM YYYY
    match = re.match(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", clean_date.upper())
    if match:
        day, month_str, year = match.groups()
        month = month_map.get(month_str)
        if month:
            return f"{year}-{month}-{int(day):02d}"

    # Только год
    match = re.match(r"^(\d{4})$", clean_date)
    if match:
        return f"{match.group(1)}-01-01"

    return None


def parse_gedcom_file(file_path: str) -> dict:
    """Парсит GEDCOM-файл напрямую, без внешних библиотек."""
    # Читаем файл с автоопределением кодировки
    content = _read_file(file_path)
    if not content:
        return {
            "persons": [],
            "families": [],
            "errors": ["Не удалось прочитать файл"],
            "total_persons": 0,
            "total_families": 0,
        }

    # Разбиваем на записи (каждая начинается с "0 ")
    records = _split_records(content)

    persons = []
    families = []
    errors = []

    for record in records:
        lines = record.strip().split("\n")
        if not lines:
            continue

        # Первая строка определяет тип записи
        first_line = lines[0].strip()

        if " INDI" in first_line or first_line.endswith("INDI"):
            try:
                person_data = _parse_individual_record(lines)
                if person_data:
                    persons.append(person_data)
            except Exception as e:
                errors.append(f"Персона: {e!s}")

        elif " FAM" in first_line or first_line.endswith("FAM"):
            try:
                family_data = _parse_family_record(lines)
                if family_data:
                    families.append(family_data)
            except Exception as e:
                errors.append(f"Семья: {e!s}")

    return {
        "persons": persons,
        "families": families,
        "errors": errors,
        "total_persons": len(persons),
        "total_families": len(families),
    }


def _read_file(file_path: str) -> str:
    """Читает файл с автоопределением кодировки."""
    for encoding in ["utf-8-sig", "utf-8", "windows-1251", "cp1251", "latin-1"]:
        try:
            with open(file_path, encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _split_records(content: str) -> list:
    """Разбивает содержимое GEDCOM на отдельные записи (начинающиеся с '0 ')."""
    records = []
    current_record = []

    for line in content.split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue

        # Запись уровня 0 начинается с "0 " или "0\t"
        if re.match(r"^0\s", line):
            if current_record:
                records.append("\n".join(current_record))
            current_record = [line]
        else:
            current_record.append(line)

    if current_record:
        records.append("\n".join(current_record))

    return records


def _extract_tag_value(line: str) -> tuple:
    """Извлекает уровень, тег и значение из строки GEDCOM."""
    match = re.match(r"^(\d+)\s+(\S+)(?:\s+(.*))?$", line)
    if not match:
        return None, None, None
    level = int(match.group(1))
    tag = match.group(2)
    value = (match.group(3) or "").strip()
    return level, tag, value


def _parse_individual_record(lines: list) -> dict | None:
    """Парсит одну запись INDI."""
    # Извлекаем pointer (например, @I356507740@)
    first_line = lines[0].strip()
    pointer_match = re.match(r"^0\s+(@[^@]+@)", first_line)
    if not pointer_match:
        return None
    pointer = pointer_match.group(1).strip("@")

    first_name = ""
    last_name = ""
    middle_name = ""
    gender = "U"
    birth_date = None
    birth_date_approx = False
    birth_place = ""
    death_date = None
    death_date_approx = False
    death_place = ""
    burial_place = ""
    notes = ""

    i = 1
    while i < len(lines):
        level, tag, value = _extract_tag_value(lines[i])
        if level is None:
            i += 1
            continue

        if level == 1:
            if tag == "NAME":
                # Формат: "First Middle /Last/ Suffix"
                name_match = re.search(r"(.+?)\s*/(.+?)/\s*(.*)", value)
                if name_match:
                    given = name_match.group(1).strip()
                    last_name = name_match.group(2).strip()

                    # Разделяем given на имя и отчество
                    parts = given.split()
                    if len(parts) >= 2:
                        first_name = parts[0]
                        middle_name = " ".join(parts[1:])
                    else:
                        first_name = given
                else:
                    first_name = value.strip()

            elif tag == "GIVN":
                if not first_name:
                    first_name = value

            elif tag == "SURN":
                if not last_name:
                    last_name = value

            elif tag == "SEX":
                gender = value.strip().upper()
                if gender not in ("M", "F"):
                    gender = "U"

            elif tag == "BIRT":
                # Ищем подтеги DATE и PLAC
                j = i + 1
                while j < len(lines):
                    sub_level, sub_tag, sub_value = _extract_tag_value(lines[j])
                    if sub_level is None or sub_level <= 1:
                        break
                    if sub_tag == "DATE" and sub_value:
                        birth_date_approx = any(
                            x in sub_value.upper() for x in ["~", "ABT", "BEF", "AFT", "CAL", "EST"]
                        )
                        birth_date = parse_date(sub_value)
                    elif sub_tag == "PLAC" and sub_value:
                        birth_place = sub_value
                    j += 1

            elif tag == "DEAT":
                # Ищем подтеги DATE и PLAC
                j = i + 1
                while j < len(lines):
                    sub_level, sub_tag, sub_value = _extract_tag_value(lines[j])
                    if sub_level is None or sub_level <= 1:
                        break
                    if sub_tag == "DATE" and sub_value:
                        death_date_approx = any(
                            x in sub_value.upper() for x in ["~", "ABT", "BEF", "AFT", "CAL", "EST"]
                        )
                        death_date = parse_date(sub_value)
                    elif sub_tag == "PLAC" and sub_value:
                        death_place = sub_value
                    j += 1

            elif tag == "BURI":
                # Ищем подтег PLAC
                j = i + 1
                while j < len(lines):
                    sub_level, sub_tag, sub_value = _extract_tag_value(lines[j])
                    if sub_level is None or sub_level <= 1:
                        break
                    if sub_tag == "PLAC" and sub_value:
                        burial_place = sub_value
                    j += 1

            elif tag == "NOTE":
                if value:
                    notes += value + "\n"

        i += 1

    # Пропускаем персон без имени
    if not first_name and not last_name:
        return None

    return {
        "gedcom_id": pointer,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "gender": gender,
        "birth_date": birth_date,
        "birth_date_approx": birth_date_approx,
        "birth_place": birth_place,
        "death_date": death_date,
        "death_date_approx": death_date_approx,
        "death_place": death_place,
        "burial_place": burial_place,
        "notes": notes.strip(),
    }


def _parse_family_record(lines: list) -> dict | None:
    """Парсит одну запись FAM."""
    first_line = lines[0].strip()
    pointer_match = re.match(r"^0\s+(@[^@]+@)", first_line)
    if not pointer_match:
        return None
    pointer = pointer_match.group(1).strip("@")

    husband_id = None
    wife_id = None
    children_ids = []
    marriage_date = None
    marriage_place = ""

    i = 1
    while i < len(lines):
        level, tag, value = _extract_tag_value(lines[i])
        if level is None:
            i += 1
            continue

        if level == 1:
            if tag == "HUSB":
                husband_id = value.strip("@")
            elif tag == "WIFE":
                wife_id = value.strip("@")
            elif tag == "CHIL":
                children_ids.append(value.strip("@"))
            elif tag == "MARR":
                # Ищем подтеги DATE и PLAC
                j = i + 1
                while j < len(lines):
                    sub_level, sub_tag, sub_value = _extract_tag_value(lines[j])
                    if sub_level is None or sub_level <= 1:
                        break
                    if sub_tag == "DATE" and sub_value:
                        marriage_date = parse_date(sub_value)
                    elif sub_tag == "PLAC" and sub_value:
                        marriage_place = sub_value
                    j += 1

        i += 1

    return {
        "gedcom_id": pointer,
        "husband_gedcom_id": husband_id,
        "wife_gedcom_id": wife_id,
        "children_gedcom_ids": children_ids,
        "marriage_date": marriage_date,
        "marriage_place": marriage_place,
    }
