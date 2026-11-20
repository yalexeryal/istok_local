# Рефакторинг person_views.py

## Текущее состояние

- `genealogy/views/person_views.py`: **1096 строк**, 7 классов
- Дублирование логики создания связей в `PersonCreateView.form_valid()` и `LinkRelativeView.post()` (~150 строк каждого)
- Дублирование логики родственников в `PersonDetailView.get_context_data()` и `PersonPDFView.get_context_data()` (~100 строк)
- Логирование и messages размазаны по view-методам

## Новая структура

```
genealogy/
├── services/
│   ├── __init__.py
│   ├── export_service.py
│   ├── import_service.py
│   └── person_service.py          # ← НОВЫЙ: создание связей
├── views/
│   ├── person_views.py            # ← РЕФАКТОРИНГ: ~700 строк → ~400 строк
│   └── ...
```

## Что переносится в person_service.py

### 1. Создание child-связей (250 строк → 1 вызов)

**Сейчас** (в `PersonCreateView.form_valid()` + `LinkRelativeView.post()`):
```python
# ~40 строк повторяющегося кода в каждом view
is_biological = self.relation in ["son", "daughter"]
rel_type = RelationshipTypeEnum.BIOLOGICAL_PARENT if is_biological else RelationshipTypeEnum.ADOPTIVE_PARENT

rel, created = Relationship.objects.get_or_create(
    from_person=self.parent1,
    to_person=person,
    relationship_type=rel_type,
    defaults={"created_by": self.request.user},
)
if created:
    log_action(...)

spouse = _get_current_spouse(self.parent1)
if spouse:
    rel2, created2 = Relationship.objects.get_or_create(...)
    if created2:
        log_action(...)

if person.birth_date:
    all_parents = [self.parent1]
    if father and father != self.parent1:
        all_parents.append(father)
    ...
    for parent in all_parents:
        LifeEvent.objects.get_or_create(...)
```

**После:**
```python
from genealogy.services.person_service import create_child_relationship

result = create_child_relationship(
    parent=self.parent1,
    child=person,
    relation_type=self.relation,
    tree=self.tree,
    user=self.request.user,
    request=self.request,
)
messages.success(self.request, result.message)
```

### 2. Создание spouse-связей (30 строк → 1 вызов)

**Сейчас:**
```python
marriage_date = self.request.POST.get("marriage_date")
marriage_place = self.request.POST.get("marriage_place")

rel, created = Relationship.objects.get_or_create(...)
if created:
    log_action(...)

for spouse in [self.spouse_of, person]:
    related = person if spouse == self.spouse_of else self.spouse_of
    LifeEvent.objects.get_or_create(...)
```

**После:**
```python
from genealogy.services.person_service import create_spouse_relationship

result = create_spouse_relationship(
    person_a=self.spouse_of,
    person_b=person,
    marriage_date=self.request.POST.get("marriage_date"),
    marriage_place=self.request.POST.get("marriage_place"),
    tree=self.tree,
    user=self.request.user,
    request=self.request,
)
messages.success(self.request, result.message)
```

### 3. Утилита _get_current_spouse

Сейчас определена в `person_views.py` (строка 37). Перенести в `person_service.py` — там она уже есть. Удалить из views.

## Порядок рефакторинга

### Шаг 1: Создать person_service.py ✅ (уже сделано)

### Шаг 2: Рефакторинг PersonCreateView.form_valid()

Заменить ~200 строк if/elif-блоков на вызовы сервисных функций:

```python
def form_valid(self, form):
    has_exact_duplicate = form.exact_duplicate is not None
    has_similar_duplicates = len(form.duplicates_found) > 0

    if (has_exact_duplicate or has_similar_duplicates) and not self.request.POST.get("force_create"):
        context = self.get_context_data(form=form)
        context["exact_duplicate"] = form.exact_duplicate
        context["duplicates_found"] = form.duplicates_found
        return self.render_to_response(context)

    response = super().form_valid(form)
    person = self.object

    # Логирование создания персоны
    from genealogy.utils.audit import get_client_ip, log_action
    log_action(
        tree=self.tree,
        user=self.request.user,
        action="CREATE",
        entity_type="PERSON",
        entity_id=person.pk,
        entity_name=person.full_name_display,
        ip_address=get_client_ip(self.request),
    )

    # === Выносим всю логику связей в сервис ===
    if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
        result = create_child_relationship(
            parent=self.parent1,
            child=person,
            relation_type=self.relation,
            tree=self.tree,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, result.message)

    elif self.spouse_of:
        result = create_spouse_relationship(
            person_a=self.spouse_of,
            person_b=person,
            marriage_date=self.request.POST.get("marriage_date"),
            marriage_place=self.request.POST.get("marriage_place"),
            tree=self.tree,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, result.message)

    elif self.parent1 and self.relation in ["father", "mother"]:
        result = create_parent_relationship(
            child=self.parent1,
            new_parent=person,
            relation_type=self.relation,
            tree=self.tree,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, result.message)

    elif self.child:
        result = create_parent_for_child_relationship(
            new_parent=person,
            child=self.child,
            tree=self.tree,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, result.message)

    else:
        messages.success(self.request, f'Персона "{person.full_name_display}" успешно создана.')

    return response
```

### Шаг 3: Рефакторинг LinkRelativeView.post()

Полностью заменить 120 строк if/elif на те же сервисные вызовы:

```python
def post(self, request, *args, **kwargs):
    selected_person = get_object_or_404(Person, pk=selected_person_id)

    if self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
        result = create_child_relationship(
            parent=self.parent1, child=selected_person, relation_type=self.relation,
            tree=self.tree, user=request.user, request=request,
        )
        messages.success(request, result.message)

    elif self.relation in ["father", "mother"]:
        result = create_parent_relationship(
            child=self.parent1, new_parent=selected_person, relation_type=self.relation,
            tree=self.tree, user=request.user, request=request,
        )
        messages.success(request, result.message)

    elif self.relation == "spouse":
        result = create_spouse_relationship(
            person_a=self.parent1, person_b=selected_person,
            tree=self.tree, user=request.user, request=request,
        )
        messages.success(request, result.message)

    return redirect("genealogy:person_detail", pk=self.parent1.pk)
```

### Шаг 4: Извлечь общую логику родственников

Создать `genealogy/utils/relatives.py` для `PersonDetailView.get_context_data()` и `PersonPDFView.get_context_data()`:

```python
# genealogy/utils/relatives.py

def get_close_relatives(person: Person) -> list[dict]:
    """
    Возвращает список близких родственников для персоны.
    Используется в PersonDetailView и PersonPDFView.
    """
    close_relatives = []

    # Родители (prefetched relationships_to)
    for rel in person.relationships_to.all():
        if rel.relationship_type in [RelationshipTypeEnum.BIOLOGICAL_PARENT, ...]:
            parent = rel.from_person
            ...
            close_relatives.append({"person": parent, "relation": rel_type, "rel_obj": rel})

    # Дети (prefetched relationships_from)
    for rel in person.relationships_from.all():
        ...

    # Супруги
    added_spouse_ids = set()
    for rel in person.relationships_from.all():
        ...
    for rel in person.relationships_to.all():
        ...

    # Братья и сёстры
    sibling_ids = set()
    for rel in person.relationships_to.all():
        ...

    return close_relatives
```

Затем в обоих views:
```python
from genealogy.utils.relatives import get_close_relatives

def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    person = self.object
    context["close_relatives"] = get_close_relatives(person)
    return context
```

## Итоговая оценка

| Метрика | До | После |
|---------|-----|-------|
| `person_views.py` строк | 1096 | ~400 |
| `_get_current_spouse` вызовов | 2 (дубликат) | 1 (в сервисе) |
| Логирование связей | ~60 строк копипасты | 0 (в сервисе) |
| LifeEvent-логика | ~30 строк копипасты | 0 (в сервисе) |
| get_close_relatives | ~100 строк × 2 views | 1 утилита |
| TDD coverage | ~80% | ожидается ~90% |

## Риски

1. **Совместимость `_log_relationship`** — текущее логирование использует `get_client_ip(request)`, сервис принимает `request`. Нужно убедиться что `_log_relationship` правильно передаёт `request` в `get_client_ip`.

2. **Transaction.atomic** — сервис оборачивает каждую операцию в `transaction.atomic()`. Если view уже имеет транзакцию, это безопасно (savepoint), но нужно проверить что нет конфликта с `form_valid()` в `PersonCreateView`.

3. **Тесты** — нужно написать тесты для `person_service.py` и убедиться что существующие `test_views.py` не ломаются.
