"""
Настройка Admin-панели Django для приложения genealogy.

Включает:
- Регистрацию всех моделей с удобными списками отображения
- Inline-редактирование событий и связей внутри персоны
- Фильтры и поиск для быстрого доступа к данным
- Кастомные действия для массовых операций
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from .models import (
    ChangeRequest,
    ChangeRequestStatusEnum,
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ExportStatusEnum,
    ExportTask,
    ExportTypeEnum,
    ImportStatusEnum,
    ImportTask,
    LifeEvent,
    Person,
    PersonStatusEnum,
    PrivacySettings,
    Relationship,
    Tree,
    TreeCollaborator,
    UserProfile,
    UserTierEnum,
)


# === INLINE КЛАССЫ (для редактирования связанных объектов) ===

class LifeEventInline(admin.TabularInline):
    """
    Inline-редактирование событий жизни внутри страницы персоны.

    Позволяет добавлять/редактировать события прямо на странице персоны,
    не переходя в отдельную админку событий.
    """
    model = LifeEvent
    fk_name = 'person'
    extra = 0
    fields = (
        'event_type',
        'event_date',
        'end_date',
        'is_date_approx',
        'location',
        'description',
    )
    ordering = ('event_date',)
    verbose_name = 'Событие жизни'
    verbose_name_plural = 'События жизни'

    def get_queryset(self, request: HttpRequest) -> QuerySet[LifeEvent]:
        """Оптимизация запросов: используем select_related."""
        return super().get_queryset(request).select_related('person', 'created_by')


class RelationshipInline(admin.TabularInline):
    """
    Inline-редактирование связей внутри страницы персоны.

    Показывает только связи, где текущая персона — источник (from_person).
    """
    model = Relationship
    fk_name = 'from_person'
    extra = 0
    fields = (
        'to_person',
        'relationship_type',
        'start_date',
        'end_date',
        'is_current',
    )
    verbose_name = 'Родственная связь'
    verbose_name_plural = 'Родственные связи'

    def get_queryset(self, request: HttpRequest) -> QuerySet[Relationship]:
        """Оптимизация запросов."""
        return super().get_queryset(request).select_related(
            'from_person', 'to_person', 'created_by'
        )


class TreeCollaboratorInline(admin.TabularInline):
    """
    Inline-редактирование соавторов внутри страницы дерева.
    """
    model = TreeCollaborator
    extra = 0
    fields = ('user', 'role', 'can_invite')
    autocomplete_fields = ('user',)
    verbose_name = 'Соавтор'
    verbose_name_plural = 'Соавторы'


# === ADMIN КЛАССЫ ===

@admin.register(Tree)
class TreeAdmin(admin.ModelAdmin):
    """
    Админка для модели Tree (генеалогическое дерево).
    """
    list_display = (
        'name',
        'get_owner_display',
        'persons_count',
        'collaborators_count',
        'is_public',
        'sync_version',
        'updated_at',
    )
    list_filter = ('is_public', 'created_at', 'updated_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at', 'sync_version', 'last_synced_at')
    inlines = [TreeCollaboratorInline]
    ordering = ('-updated_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'is_public'),
        }),
        ('Синхронизация', {
            'fields': ('sync_version', 'last_synced_at'),
            'classes': ('collapse',),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Владелец', ordering='collaborators__user')
    def get_owner_display(self, obj: Tree) -> str:
        """Получить владельца дерева для отображения в списке."""
        owner = obj.get_owner()
        return owner.username if owner else '—'

    @admin.display(description='Персон')
    def persons_count(self, obj: Tree) -> int:
        """Количество персон в дереве."""
        return obj.persons.count()

    @admin.display(description='Соавторов')
    def collaborators_count(self, obj: Tree) -> int:
        """Количество соавторов дерева."""
        return obj.collaborators.count()


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """
    Админка для модели Person (персона).

    Включает inline-редактирование событий и связей.
    """
    list_display = (
        'full_name_display',
        'get_tree_name',
        'gender',
        'birth_date',
        'death_date',
        'get_age_display',
        'status',
        'updated_at',
    )
    list_filter = (
        'gender',
        'status',
        'tree',
        'is_birth_date_approx',
        'is_death_date_approx',
        'created_at',
    )
    search_fields = (
        'first_name',
        'middle_name',
        'last_name',
        'maiden_name',
        'birth_place',
        'notes',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'sync_version',
        'last_synced_at',
        'photo_preview',
    )
    inlines = [LifeEventInline, RelationshipInline]
    autocomplete_fields = ('tree', 'merged_into', 'updated_by')
    ordering = ('last_name', 'first_name')

    fieldsets = (
        ('Основные данные', {
            'fields': (
                'tree',
                'first_name',
                'middle_name',
                'last_name',
                'maiden_name',
                'gender',
            ),
        }),
        ('Даты жизни', {
            'fields': (
                ('birth_date', 'is_birth_date_approx'),
                ('death_date', 'is_death_date_approx'),
            ),
        }),
        ('Места', {
            'fields': ('birth_place', 'death_place', 'burial_place'),
        }),
        ('Дополнительно', {
            'fields': ('culture', 'photo', 'photo_preview', 'notes'),
        }),
        ('Статус', {
            'fields': ('status', 'merged_into'),
        }),
        ('Синхронизация', {
            'fields': ('sync_version', 'last_synced_at', 'updated_by'),
            'classes': ('collapse',),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Дерево', ordering='tree__name')
    def get_tree_name(self, obj: Person) -> str:
        """Название дерева для отображения в списке."""
        return obj.tree.name

    @admin.display(description='Возраст')
    def get_age_display(self, obj: Person) -> str:
        """Возраст или статус для отображения."""
        age = obj.age
        if age is None:
            return '—'
        if obj.is_alive:
            return f'{age} лет'
        return f'†{age}'

    @admin.display(description='Фото')
    def photo_preview(self, obj: Person) -> str:
        """Превью фотографии в админке."""
        if obj.photo:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.photo.url
            )
        return '—'

    actions = ['mark_as_published', 'mark_as_sandbox']

    @admin.action(description='Опубликовать выбранных персон')
    def mark_as_published(self, request: HttpRequest, queryset: QuerySet[Person]) -> None:
        """Массовое изменение статуса на 'Опубликовано'."""
        count = queryset.update(status=PersonStatusEnum.PUBLISHED)
        self.message_user(request, f'Опубликовано персон: {count}')

    @admin.action(description='Вернуть в черновики')
    def mark_as_sandbox(self, request: HttpRequest, queryset: QuerySet[Person]) -> None:
        """Массовое изменение статуса на 'Черновик'."""
        count = queryset.update(status=PersonStatusEnum.SANDBOX)
        self.message_user(request, f'Возвращено в черновики: {count}')


@admin.register(LifeEvent)
class LifeEventAdmin(admin.ModelAdmin):
    """
    Админка для модели LifeEvent (событие жизни).
    """
    list_display = (
        'get_person_name',
        'event_type',
        'event_date',
        'location',
        'created_at',
    )
    list_filter = ('event_type', 'is_date_approx', 'event_date', 'created_at')
    search_fields = (
        'person__first_name',
        'person__last_name',
        'location',
        'description',
    )
    readonly_fields = ('created_at', 'updated_at', 'sync_version', 'last_synced_at')
    autocomplete_fields = ('person', 'related_person', 'created_by')
    ordering = ('-event_date',)

    @admin.display(description='Персона', ordering='person__last_name')
    def get_person_name(self, obj: LifeEvent) -> str:
        """Имя персоны для отображения в списке."""
        return obj.person.full_name_display


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    """
    Админка для модели Relationship (родственная связь).
    """
    list_display = (
        'from_person',
        'relationship_type',
        'to_person',
        'is_current',
        'start_date',
    )
    list_filter = ('relationship_type', 'is_current', 'created_at')
    search_fields = (
        'from_person__first_name',
        'from_person__last_name',
        'to_person__first_name',
        'to_person__last_name',
    )
    readonly_fields = ('created_at', 'updated_at', 'sync_version', 'last_synced_at')
    autocomplete_fields = ('from_person', 'to_person', 'created_by')
    ordering = ('-created_at',)


@admin.register(TreeCollaborator)
class TreeCollaboratorAdmin(admin.ModelAdmin):
    """
    Админка для модели TreeCollaborator (соавтор дерева).
    """
    list_display = ('user', 'tree', 'role', 'can_invite', 'created_at')
    list_filter = ('role', 'can_invite', 'created_at')
    search_fields = ('user__username', 'user__email', 'tree__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user', 'tree')
    ordering = ('-created_at',)


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    """
    Админка для модели ChangeRequest (запрос на изменение).
    """
    list_display = (
        'id',
        'person',
        'change_type',
        'status',
        'requested_by',
        'created_at',
        'responded_at',
    )
    list_filter = ('status', 'change_type', 'created_at')
    search_fields = (
        'person__first_name',
        'person__last_name',
        'requested_by__username',
        'response_comment',
    )
    readonly_fields = ('created_at',)
    autocomplete_fields = ('person', 'requested_by', 'owner')
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('person', 'change_type', 'status'),
        }),
        ('Участники', {
            'fields': ('requested_by', 'owner'),
        }),
        ('Данные изменения', {
            'fields': ('proposed_data',),
        }),
        ('Ответ', {
            'fields': ('responded_at', 'response_comment'),
        }),
        ('Системная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Админка для модели UserProfile (профиль пользователя).
    """
    list_display = (
        'user',
        'tier',
        'tier_expires_at',
        'devices_count',
        'created_at',
    )
    list_filter = ('tier', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user',)
    ordering = ('-created_at',)

    fieldsets = (
        ('Пользователь', {
            'fields': ('user',),
        }),
        ('Тариф', {
            'fields': ('tier', 'tier_expires_at'),
        }),
        ('Устройства', {
            'fields': ('devices_count',),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


# === АДМИНКА ДЛЯ ЭКСПОРТ/ИМПОРТ ===

@admin.register(PrivacySettings)
class PrivacySettingsAdmin(admin.ModelAdmin):
    """Админка для модели PrivacySettings."""
    list_display = (
        'user',
        'hide_birth_date',
        'hide_notes',
        'hide_photos',
        'full_data_min_degree',
    )
    list_filter = ('hide_birth_date', 'hide_notes', 'hide_photos')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user',)

    fieldsets = (
        ('Пользователь', {
            'fields': ('user',),
        }),
        ('Скрытие данных', {
            'fields': (
                'hide_birth_date',
                'hide_death_date',
                'hide_birth_place',
                'hide_death_place',
                'hide_notes',
                'hide_photos',
            ),
        }),
        ('Степень родства', {
            'fields': ('full_data_min_degree',),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ExportTask)
class ExportTaskAdmin(admin.ModelAdmin):
    """Админка для модели ExportTask."""
    list_display = (
        'id',
        'user',
        'tree',
        'export_type',
        'export_format',
        'status',
        'person_count',
        'created_at',
    )
    list_filter = ('status', 'export_type', 'export_format', 'created_at')
    search_fields = ('user__username', 'tree__name')
    readonly_fields = (
        'created_at',
        'completed_at',
        'file_size',
        'person_count',
        'error_message',
    )
    autocomplete_fields = ('user', 'tree', 'target_person')
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'tree', 'export_type', 'export_format'),
        }),
        ('Для родственника', {
            'fields': ('target_person', 'privacy_overrides'),
            'classes': ('collapse',),
        }),
        ('Статус', {
            'fields': ('status', 'file', 'file_size', 'person_count'),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'completed_at', 'error_message'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ImportTask)
class ImportTaskAdmin(admin.ModelAdmin):
    """Админка для модели ImportTask."""
    list_display = (
        'id',
        'user',
        'tree',
        'import_format',
        'status',
        'person_count',
        'created_at',
    )
    list_filter = ('status', 'import_format', 'created_at')
    search_fields = ('user__username', 'tree__name')
    readonly_fields = (
        'created_at',
        'completed_at',
        'person_count',
        'relationship_count',
        'error_message',
    )
    autocomplete_fields = ('user', 'tree')
    ordering = ('-created_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'tree', 'import_format', 'source_file'),
        }),
        ('Статус', {
            'fields': (
                'status',
                'person_count',
                'relationship_count',
            ),
        }),
        ('Системная информация', {
            'fields': ('created_at', 'completed_at', 'error_message'),
            'classes': ('collapse',),
        }),
    )


# === РЕГИСТРАЦИЯ ПРОФИЛЯ ВНУТРИ USER ADMIN ===

class UserProfileInline(admin.StackedInline):
    """
    Inline-редактирование профиля внутри страницы пользователя.
    """
    model = UserProfile
    can_delete = False
    verbose_name = 'Профиль istok_local'
    verbose_name_plural = 'Профиль istok_local'
    fk_name = 'user'


class CustomUserAdmin(BaseUserAdmin):
    """
    Кастомная админка для встроенной модели User.
    """
    inlines = BaseUserAdmin.inlines + (UserProfileInline,)


# Перерегистрируем User с нашей кастомной админкой
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# === НАСТРОЙКА ЗАГОЛОВКОВ АДМИНКИ ===

admin.site.site_header = 'Исток — Управление генеалогическими данными'
admin.site.site_title = 'Исток Админ'
admin.site.index_title = 'Добро пожаловать в систему Исток'