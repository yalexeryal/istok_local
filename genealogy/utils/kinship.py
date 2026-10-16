"""
Сервис для вычисления сетей родства в генеалогическом дереве.
Реализует строгие правила обхода графа родства, исключающие "утечку" в семьи супругов.
"""

from collections import defaultdict

from genealogy.models import Person, Relationship, RelationshipTypeEnum


def get_kinship_network(
    center_person: Person,
    include_spouses: bool = True,
    include_adoptive: bool = True,
    include_ex_spouses: bool = True,
) -> set[int]:
    """
    Возвращает множество ID персон, образующих сеть родства относительно center_person.

    Правила обхода (строго по ТЗ):
    1. Находим всех биологических (и опционально приёмных) предков center_person.
    2. Находим всех потомков этих предков (это даёт саму персону, братьев, сестёр, кузенов, детей, внуков).
       ВАЖНО: При движении вниз мы НЕ идём "вверх" к другим родителям найденных детей.
    3. Если include_spouses=True, находим всех супругов людей из п.1 и п.2.
       ВАЖНО: От этих супругов мы НЕ идём ни вверх (к их родителям), ни вниз (к их детям от других браков).
    4. Если include_ex_spouses=True, добавляем бывших супругов (но их новую родню всё равно не трогаем).

    Args:
        center_person: Центральная персона, относительно которой строится сеть
        include_spouses: Включать текущих супругов кровных родственников
        include_adoptive: Включать приёмных родителей/детей как кровных
        include_ex_spouses: Включать бывших супругов (разведённых)

    Returns:
        Set[int]: Множество ID персон, входящих в сеть родства
    """
    tree = center_person.tree
    visited_blood = set()

    # Определяем типы связей, которые считаем "кровными"
    blood_parent_types = [RelationshipTypeEnum.BIOLOGICAL_PARENT]
    if include_adoptive:
        blood_parent_types.append(RelationshipTypeEnum.ADOPTIVE_PARENT)

    # Загружаем все родительские связи дерева ОДИН раз для максимальной скорости
    parent_rels = list(
        Relationship.objects.filter(from_person__tree=tree, relationship_type__in=blood_parent_types).values_list(
            "from_person_id", "to_person_id"
        )
    )

    # Строим словари смежности для мгновенного поиска в памяти
    parents_of = defaultdict(list)  # child_id -> [parent_id, ...]
    children_of = defaultdict(list)  # parent_id -> [child_id, ...]

    for parent_id, child_id in parent_rels:
        parents_of[child_id].append(parent_id)
        children_of[parent_id].append(child_id)

    # === ШАГ 1: Находим всех ПРЕДКОВ (идём вверх от центральной персоны) ===
    queue_up = [center_person.pk]
    while queue_up:
        current = queue_up.pop(0)
        if current not in visited_blood:
            visited_blood.add(current)
            # Добавляем родителей, но НЕ идём от них дальше в этом цикле
            # (мы пойдём от них вниз в шаге 2)
            queue_up.extend(parents_of.get(current, []))

    # === ШАГ 2: Находим всех ПОТОМКОВ этих предков ===
    # Это захватывает саму персону, её братьев/сестер, племянников, кузенов, детей, внуков
    # ВАЖНО: Мы НЕ идём "вверх" к другим родителям найденных детей
    queue_down = list(visited_blood)
    while queue_down:
        current = queue_down.pop(0)
        for child in children_of.get(current, []):
            if child not in visited_blood:
                visited_blood.add(child)
                queue_down.append(child)

    # === ШАГ 3: Добавляем СУПРУГОВ всех найденных кровных родственников ===
    # ВАЖНО: Мы добавляем их в список, но НЕ добавляем их в queue_down,
    # чтобы алгоритм не пошёл искать родителей или братьев этого супруга
    if include_spouses or include_ex_spouses:
        spouse_rels = Relationship.objects.filter(
            from_person__tree=tree, relationship_type=RelationshipTypeEnum.SPOUSE
        ).values_list("from_person_id", "to_person_id", "end_date")

        for p1, p2, end_date in spouse_rels:
            # Проверяем, является ли один из супругов кровным родственником
            if p1 in visited_blood and p2 not in visited_blood:
                # p1 - кровный, p2 - его супруг
                if end_date is None:
                    # Текущий брак
                    if include_spouses:
                        visited_blood.add(p2)
                else:
                    # Бывший брак
                    if include_ex_spouses:
                        visited_blood.add(p2)
            elif p2 in visited_blood and p1 not in visited_blood:
                # p2 - кровный, p1 - его супруг
                if end_date is None:
                    if include_spouses:
                        visited_blood.add(p1)
                else:
                    if include_ex_spouses:
                        visited_blood.add(p1)

    return visited_blood
