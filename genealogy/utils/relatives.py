"""
Утилиты для получения информации о близких родственниках персоны.

Централизует логику из PersonDetailView и PersonPDFView.
Использует уже предвыбранные (prefetched) связи для эффективности.
"""


from genealogy.models import Person, RelationshipTypeEnum


def get_close_relatives(person: Person) -> tuple[list[dict], Person | None, Person | None]:
    """
    Возвращает кортеж (close_relatives, father, mother).

    close_relatives — список dict с ключами:
        - person: Person
        - relation: str (человекеческое название связи)
        - rel_obj: Relationship | None

    father / mother — первые найденные объекты для удобного доступа в шаблонах.
    """
    close_relatives: list[dict] = []
    father: Person | None = None
    mother: Person | None = None

    # === 1. РОДИТЕЛИ (current person = to_person, parent = from_person) ===
    for rel in person.relationships_to.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
            RelationshipTypeEnum.STEP_PARENT,
        ):
            parent = rel.from_person
            if not parent:
                continue

            gender = parent.gender
            if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                rel_type = "Отец (Родной)" if gender == "male" else "Мать (Родная)"
            elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                rel_type = "Отец (Приемный)" if gender == "male" else "Мать (Приемная)"
            else:
                rel_type = "Отчим" if gender == "male" else "Мачеха"

            close_relatives.append({"person": parent, "relation": rel_type, "rel_obj": rel})

            if gender == "male":
                father = parent
            else:
                mother = parent

    # === 2. ДЕТИ (current person = from_person, child = to_person) ===
    for rel in person.relationships_from.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
        ):
            child = rel.to_person
            if not child:
                continue

            gender = child.gender
            rel_type = "Сын" if gender == "male" else "Дочь"
            close_relatives.append({"person": child, "relation": rel_type, "rel_obj": rel})

    # === 3. СУПРУГИ (могут быть и в from, и в to) ===
    added_spouse_ids: set[int] = set()

    for rel in person.relationships_from.all():
        if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
            spouse = rel.to_person
            if spouse and spouse.pk not in added_spouse_ids:
                if rel.end_date:
                    rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                else:
                    rel_type = "Жена" if spouse.gender == "female" else "Муж"
                close_relatives.append({"person": spouse, "relation": rel_type, "rel_obj": rel})
                added_spouse_ids.add(spouse.pk)

    for rel in person.relationships_to.all():
        if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
            spouse = rel.from_person
            if spouse and spouse.pk not in added_spouse_ids:
                if rel.end_date:
                    rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                else:
                    rel_type = "Жена" if spouse.gender == "female" else "Муж"
                close_relatives.append({"person": spouse, "relation": rel_type, "rel_obj": rel})
                added_spouse_ids.add(spouse.pk)

    # === 4. БРАТЬЯ И СЕСТРЫ (общий родитель) ===
    sibling_ids: set[int] = set()

    for rel in person.relationships_to.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
        ):
            parent = rel.from_person
            for child_rel in parent.relationships_from.all():
                if child_rel.relationship_type in (
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                ):
                    sibling = child_rel.to_person
                    if sibling and sibling.pk != person.pk and sibling.pk not in sibling_ids:
                        sibling_ids.add(sibling.pk)
                        rel_type = "Брат" if sibling.gender == "male" else "Сестра"
                        close_relatives.append({"person": sibling, "relation": rel_type})

    return close_relatives, father, mother


def get_close_relatives_for_pdf(person: Person) -> list[dict]:
    """
    Упрощённая версия для PDF (без rel_obj, без father/mother).

    Используется в PersonPDFView.get_context_data().
    """
    close_relatives: list[dict] = []

    # Родители
    for rel in person.relationships_to.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
            RelationshipTypeEnum.STEP_PARENT,
        ):
            parent = rel.from_person
            if not parent:
                continue

            gender = parent.gender
            if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                rel_type = "Отец (Родной)" if gender == "male" else "Мать (Родная)"
            elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                rel_type = "Отец (Приемный)" if gender == "male" else "Мать (Приемная)"
            else:
                rel_type = "Отчим" if gender == "male" else "Мачеха"

            close_relatives.append({"person": parent, "relation": rel_type})

    # Дети
    for rel in person.relationships_from.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
        ):
            child = rel.to_person
            if not child:
                continue

            gender = child.gender
            rel_type = "Сын" if gender == "male" else "Дочь"
            close_relatives.append({"person": child, "relation": rel_type})

    # Супруги
    added_spouse_ids: set[int] = set()

    for rel in person.relationships_from.all():
        if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
            spouse = rel.to_person
            if spouse and spouse.pk not in added_spouse_ids:
                rel_type = "Жена" if spouse.gender == "female" else "Муж"
                if rel.end_date:
                    rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                close_relatives.append({"person": spouse, "relation": rel_type})
                added_spouse_ids.add(spouse.pk)

    for rel in person.relationships_to.all():
        if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
            spouse = rel.from_person
            if spouse and spouse.pk not in added_spouse_ids:
                rel_type = "Жена" if spouse.gender == "female" else "Муж"
                if rel.end_date:
                    rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                close_relatives.append({"person": spouse, "relation": rel_type})
                added_spouse_ids.add(spouse.pk)

    # Братья и сёстры
    sibling_ids: set[int] = set()

    for rel in person.relationships_to.all():
        if rel.relationship_type in (
            RelationshipTypeEnum.BIOLOGICAL_PARENT,
            RelationshipTypeEnum.ADOPTIVE_PARENT,
        ):
            parent = rel.from_person
            for child_rel in parent.relationships_from.all():
                if child_rel.relationship_type in (
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                ):
                    sibling = child_rel.to_person
                    if sibling and sibling.pk != person.pk and sibling.pk not in sibling_ids:
                        sibling_ids.add(sibling.pk)
                        rel_type = "Брат" if sibling.gender == "male" else "Сестра"
                        close_relatives.append({"person": sibling, "relation": rel_type})

    return close_relatives
