# 🛠️ Руководство разработчика — Исток

Это руководство предназначено для разработчиков, которые хотят понять архитектуру проекта, внести изменения или расширить функциональность.

---

## 📑 Содержание

1. [Архитектура проекта](#архитектура-проекта)
2. [Установка для разработки](#установка-для-разработки)
3. [Структура моделей](#структура-моделей)
4. [API endpoints](#api-endpoints)
5. [Фронтенд](#фронтенд)
6. [Тестирование](#тестирование)
7. [Развёртывание](#развёртывание)
8. [Соглашения о коде](#соглашения-о-коде)

---

## 🏗️ Архитектура проекта

### Общие принципы
- **Backend:** Django 5.1 + Python 3.12
- **Frontend:** HTML5 + Tailwind CSS + Alpine.js
- **Визуализация:** Cytoscape.js + dagre (для графов), Chart.js (для графиков)
- **БД:** SQLite (разработка) / PostgreSQL (продакшн)
- **Линтер:** Ruff

### Структура приложения `genealogy`
```
text
istok_local/
├── pyproject.toml              # Зависимости (основные и dev)
├── pytest.ini                  # Конфигурация pytest
├── manage.py                   # CLI утилита Django
├── media/                      # 📁 Загруженные файлы (фотографии, экспорт)
├── static/                     # 📁 Статические файлы (CSS, JS, изображения)
│
├── docs/
│   ├── user_guide.md           # Инструкции для конечных пользователей
│   └── dev_guide.md            # Этот файл
│
├── istok_local/                # Настройки проекта
│   ├── __init__.py
│   ├── settings.py             # DEBUG, DATABASES, INSTALLED_APPS, MIDDLEWARE
│   └── urls.py                 # Корневой роутинг (включает genealogy.urls)
│
└── genealogy/                  # Основное приложение
    ├── __init__.py
    ├── admin.py                # Регистрация моделей в Django Admin
    ├── apps.py                 # Конфигурация приложения (GenealogyConfig)
    ├── signals.py              # Сигналы (post_save, pre_delete и т.д.)
    ├── urls.py                 # Маршруты приложения
    │
    ├── models/                 # 🗄️ Модели данных (декомпозированы)
    │   ├── __init__.py         # Экспорт всех моделей для удобного импорта
    │   ├── audit.py            # AuditLog (история изменений)
    │   ├── enums.py            # Все перечисления (EventTypeEnum, RelationshipTypeEnum и др.)
    │   ├── events.py           # LifeEvent (события жизни)
    │   ├── export_import.py    # ExportTask, ImportTask (очереди задач)
    │   ├── person.py           # Person, PersonPhoto
    │   ├── relationships.py    # Relationship (связи между персонами)
    │   ├── tree.py             # Tree, TreeCollaborator
    │   └── users.py            # UserProfile, PrivacySettings, ChangeRequest
    │
    ├── views/                  # 🌐 Обработчики запросов
    │   ├── __init__.py
    │   ├── api_views.py        # REST API endpoints (JSON)
    │   ├── auth_views.py       # Аутентификация и регистрация
    │   ├── event_views.py      # CRUD событий жизни
    │   ├── export_views.py     # Экспорт/импорт данных (CSV, JSON)
    │   ├── person_views.py     # CRUD персон и управление фотографиями
    │   ├── relationship_views.py # Управление связями
    │   └── tree_views.py       # Деревья, статистика, поиск, история (Audit Log)
    │
    ├── forms/                  # 📝 Django-формы
    │   ├── __init__.py
    │   ├── event_forms.py      # LifeEventForm (включая логику "умного развода")
    │   ├── export_import_forms.py
    │   ├── person_forms.py     # PersonForm (с проверкой дубликатов)
    │   ├── relationship_forms.py
    │   └── tree_forms.py
    │
    ├── services/               # ⚙️ Бизнес-логика (Service Layer)
    │   ├── __init__.py
    │   ├── export_service.py   # Логика генерации файлов экспорта
    │   └── import_service.py   # Логика парсинга и импорта данных
    │
    ├── utils/                  # 🛠️ Вспомогательные функции
    │   ├── __init__.py
    │   ├── audit.py            # log_action(), get_client_ip()
    │   └── names.py            # Склонение фамилий, генерация отчеств
    │
    ├── templatetags/           # 🏷️ Кастомные теги шаблонов
    │   ├── __init__.py
    │   └── tree_tags.py
    │
    ├── templates/              # 🎨 HTML-шаблоны
    │   ├── base.html           # Базовый шаблон с Tailwind CSS и Alpine.js
    │   ├── genealogy/          # Шаблоны приложения (tree_detail.html, person_detail.html и др.)
    │   └── registration/       # Шаблоны входа, регистрации, смены пароля
    │
    ├── migrations/             # 🔄 Миграции базы данных
    │   └── ...                 # Автогенерируемые файлы миграций
    │
    └── tests/                  # 🧪 Тесты
        ├── __init__.py
        ├── test_admin.py       # Тесты админ-панели
        ├── test_export_service.py
        ├── test_forms.py       # Тесты валидации форм
        ├── test_import_service.py
        ├── test_models.py      # Тесты бизнес-логики моделей
        ├── test_names.py       # Тесты утилит склонения имен
        ├── test_setup.py       # Фикстуры и базовые настройки тестов
        └── test_views.py       # Тесты HTTP-ответов и прав доступа
```

---

## 🚀 Установка для разработки

### 1. Клонирование и окружение

```bash
git clone https://github.com/yalexeryal/istok_local.git
cd istok_local
python -m venv venv
venv\Scripts\activate  # Windows
pip install -e ".[dev]"
```
## 2. Настройка БД
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```
## 3. Запуск
```bash
python manage.py runserver
```
## 4. Линтер
```bash
ruff check .           # Проверка
ruff check . --fix     # Автоисправление
```
## 📦 Структура моделей
### Person (Персона)
~~~
class Person(models.Model):
    tree = ForeignKey(Tree)
    first_name, middle_name, last_name, maiden_name
    gender  # male/female/unknown
    birth_date, death_date
    is_birth_date_approx, is_death_date_approx
    birth_place, death_place, burial_place
    culture
    photo  # основное фото (FileField)
    notes
~~~
## Relationship (Связь)
~~~
class Relationship(models.Model):
    from_person, to_person  # ForeignKey(Person)
    relationship_type  # BIOLOGICAL_PARENT, SPOUSE, и др.
    start_date, end_date
    is_current
    description
~~~
## Типы связей (RelationshipTypeEnum):
- BIOLOGICAL_PARENT — биологический родитель
- ADOPTIVE_PARENT — приёмный родитель
- STEP_PARENT — сводный родитель (отчим/мачеха)
- SPOUSE — супруг
- EX_SPOUSE — бывший супруг
- FIANCE — жених/невеста
## LifeEvent (Событие жизни)
~~~
class LifeEvent(models.Model):
    person = ForeignKey(Person)
    event_type  # MARRIAGE, DIVORCE, BIRTH_OF_CHILD, и др.
    event_date, end_date
    is_date_approx
    location, description
    related_person = ForeignKey(Person, null=True)
~~~
## AuditLog (Лог действий)
~~~
class AuditLog(models.Model):
    tree, user
    action  # CREATE, UPDATE, DELETE
    entity_type  # PERSON, EVENT, PHOTO, RELATIONSHIP
    entity_id, entity_name
    details  # JSONField
    timestamp, ip_address
~~~
## 🌐 API Endpoints
### Публичные API (требуют аутентификации)
~~~
|URL                            |Метод      |Описание                    |
|_______________________________|___________|____________________________|
|/api/tree/<pk>/hierarchy/      |GET        |Данные для графа            |
|/api/tree/<pk>/ancestors/      |GET        |Предки для веерной диаграммы|
|/api/tree/<pk>/statistics/     |GET        |Статистика дерева           |
|/api/tree/<pk>/upcoming-events/|GET        |Ближайшие события           |
|_______________________________|___________|____________________________|            
~~~
### Пример запроса статистики
~~~
GET /api/tree/2/statistics/?scope=relatives&center_person=9
~~~
### Ответ:
~~~ 
json
{
  "basic": {
    "total": 22,
    "filtered_count": 15,
    "males": 8,
    "females": 7
  },
  "ages": {...},
  "decades": {...},
  "birth_places": {...},
  "marriages": {...}
}
~~~
## 🎨 Фронтенд
### Используемые библиотеки
- Tailwind CSS — утилитарные CSS-классы
- Alpine.js — реактивность в шаблонах
- Cytoscape.js — визуализация графов
- d- agre — алгоритм иерархической раскладки
- Chart.js — графики статистики
### Ключевые шаблоны
~~~
tree_detail.html
~~~
- Главный шаблон страницы дерева
- Содержит 4 режима визуализации
- Боковая панель с карточкой персоны
- Виджет ближайших событий
- person_detail.html
- Карточка персоны
- Галерея фотографий
- Хронология жизни
- Ближайшие родственники
### Работа с графом (Cytoscape)
~~~
// Инициализация
cy = cytoscape({
    container: document.getElementById('cy'),
    elements: prepareElements(data),
    style: [...],
    layout: {...}
});

// Обработка клика
cy.on('tap', 'node', function(evt) {
    showPersonSidebar(evt.target.id(), evt.target.data());
});
~~~
## 🧪 Тестирование
```bash
python manage.py test
```

### Покрытие кода
```bash
pip install coverage
coverage run manage.py test
coverage report
```
### Ручное тестирование
Чек-лист перед релизом:
- Создание/редактирование/удаление персоны
- Установка всех типов связей
- Создание событий (особенно развод)
- Загрузка и удаление фото
- Все 4 режима визуализации
- Расширенный поиск (кириллица, регистр)
- Статистика (все графики)
- История изменений
- Мобильная версия
## 🚢 Развёртывание
### Production-настройки
1. Переменные окружения (.env):
```env
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com
DATABASE_URL=postgres://user:pass@host:5432/dbname
```

2. Статические файлы:
```bash
python manage.py collectstatic
```

3. БД: PostgreSQL вместо SQLite
4. WSGI-сервер: Gunicorn + Nginx
Docker (опционально)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "istok_local.wsgi:application", "--bind", "0.0.0.0:8000"]
```
## 📝 Соглашения о коде
### Стиль
- Ruff — линтер и форматтер
- Максимальная длина строки: 120 символов
- Использовать type hints где возможно
### Именование
- Модели: CamelCase (например, Person, LifeEvent)
- Функции/методы: snake_case (например, get_full_name)
- Константы/enum: UPPER_SNAKE_CASE
- URL names: snake_case (например, person_detail)
### Структура view
~~~
class PersonCreateView(LoginRequiredMixin, CreateView):
    """Краткое описание."""
    
    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"
    
    def dispatch(self, request, *args, **kwargs):
        # Проверка прав
        ...
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Дополнительный контекст
        ...
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        # Логирование, уведомления
        ...
        return response
~~~
### Логирование действий
Всегда используйте утилиту  `log_action`:
~~~
from genealogy.utils.audit import log_action, get_client_ip

log_action(
    tree=tree,
    user=request.user,
    action="CREATE",
    entity_type="PERSON",
    entity_id=person.pk,
    entity_name=person.full_name_display,
    ip_address=get_client_ip(request),
)
~~~
## 🔧 Полезные команды
```bash
# Установить проект для разработки
pip install -e ".[dev]"

# Создать миграции (после изменения моделей)
python manage.py makemigrations

# Применить миграции
python manage.py migrate

# Создать суперпользователя
python manage.py createsuperuser

# Открыть интерактивный shell
python manage.py shell

# Запустить тесты
python manage.py test

# Проверить код линтером
ruff check .

# Автоисправление проблем
ruff check . --fix
```


## 🐛 Отладка
### Режим DEBUG
В `settings.py`:
```
DEBUG = True  # Только для разработки!
```
### Логи
Смотрите вывод `python manage.py runserver` — там отображаются все SQL-запросы и ошибки.
### Django Debug Toolbar
Установите для детальной отладки:
```bash
pip install django-debug-toolbar
```

## 📚 Полезные ссылки
- [Django Documentation](https://docs.djangoproject.com/?spm=a2ty_o01.29997173.0.0.7c5fc921932vWq)
- [Cytoscape.js](https://js.cytoscape.org/?spm=a2ty_o01.29997173.0.0.7c5fc921932vWq)
- [Alpine.js](https://alpinejs.dev/?spm=a2ty_o01.29997173.0.0.7c5fc921932vWq)
- [Tailwind CSS](https://tailwindcss.com/?spm=a2ty_o01.29997173.0.0.7c5fc921932vWq)
- [Chart.js](https://www.chartjs.org/?spm=a2ty_o01.29997173.0.0.7c5fc921932vWq)
## 🤝 Вклад в проект
1. Создайте ветку: `git checkout -b feature/my-feature`
1. Внесите изменения
1. Проверьте линтером: `ruff check .`
1. Закоммитьте: `git commit -m "feat: описание"`
1. Запушьте: `git push origin feature/my-feature`
1. Создайте Pull Request
## Спасибо за интерес к проекту Исток! 🌳