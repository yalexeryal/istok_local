"""
Модели данных для генеалогического приложения istok_local.

Включает модели для:
- Генеалогических деревьев (Tree)
- Персон (Person)
- Событий жизни (LifeEvent)
- Родственных связей (Relationship)
- Соавторов деревьев (TreeCollaborator)
- Запросов на изменения (ChangeRequest)
"""
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone


# === ENUMS (Перечисления) ===

class GenderEnum(models.TextChoices):
    """Пол персоны."""
    MALE = 'male', 'Мужской'
    FEMALE = 'female', 'Женский'
    UNKNOWN = 'unknown', 'Неизвестно'


class EventTypeEnum(models.TextChoices):
    """Типы событий жизни."""
    BIRTH = 'birth', 'Рождение'
    DEATH = 'death', 'Смерть'
    MARRIAGE = 'marriage', 'Брак'
    DIVORCE = 'divorce', 'Развод'
    BIRTH_OF_CHILD = 'birth_of_child', 'Рождение ребенка'
    EDUCATION = 'education', 'Образование'
    WORK = 'work', 'Работа'
    MILITARY_SERVICE = 'military', 'Военная служба'
    MIGRATION = 'migration', 'Миграция'
    RELIGIOUS_EVENT = 'religious_event', 'Религиозное событие'
    OTHER = 'other', 'Другое'


class RelationshipTypeEnum(models.TextChoices):
    """Типы родственных связей."""
    BIOLOGICAL_PARENT = 'biological_parent', 'Биологический родитель'
    ADOPTIVE_PARENT = 'adoptive_parent', 'Приемный родитель'
    STEP_PARENT = 'step_parent', 'Отчим/мачеха'
    SPOUSE = 'spouse', 'Супруг(а)'
    EX_SPOUSE = 'ex_spouse', 'Бывший супруг(а)'
    FIANCE = 'fiance', 'Жених/невеста'
    GUARDIAN = 'guardian', 'Опекун'
    GODPARENT = 'godparent', 'Крестный родитель'


class CollaboratorRoleEnum(models.TextChoices):
    """Роли соавторов дерева."""
    OWNER = 'owner', 'Владелец'
    EDITOR = 'editor', 'Редактор'
    VIEWER = 'viewer', 'Читатель'


class ChangeRequestStatusEnum(models.TextChoices):
    """Статусы запросов на изменения."""
    PENDING = 'pending', 'Ожидает'
    APPROVED = 'approved', 'Одобрен'
    REJECTED = 'rejected', 'Отклонен'
    AUTO_APPROVED = 'auto_approved', 'Автоматически одобрен'


class PersonStatusEnum(models.TextChoices):
    """Статусы персоны."""
    SANDBOX = 'sandbox', 'Черновик'
    PUBLISHED = 'published', 'Опубликовано'
    MERGED = 'merged', 'Объединена'


class UserTierEnum(models.TextChoices):
    """Тарифы пользователей."""
    FREE = 'free', 'Бесплатный'
    ONE_TIME = 'one_time', 'Единоразовая оплата'
    SUBSCRIPTION = 'subscription', 'Подписка'


# === MODELS (Модели) ===

class Tree(models.Model):
    """
    Модель генеалогического дерева.

    Каждое дерево имеет уникальное имя и может иметь нескольких соавторов.
    """
    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Название',
        help_text='Уникальное название дерева'
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Описание'
    )
    is_public = models.BooleanField(
        default=False,
        verbose_name='Публичное дерево',
        help_text='Если отмечено, дерево доступно всем пользователям'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    # Поля для синхронизации
    sync_version = models.IntegerField(
        default=0,
        verbose_name='Версия синхронизации',
        help_text='Увеличивается при каждом изменении'
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последняя синхронизация'
    )

    class Meta:
        verbose_name = 'Дерево'
        verbose_name_plural = 'Деревья'
        ordering = ['-updated_at']

    def __str__(self) -> str:
        """Строковое представление дерева."""
        return self.name

    def get_absolute_url(self) -> str:
        """URL детальной страницы дерева."""
        return reverse('genealogy:tree_detail', kwargs={'pk': self.pk})

    def get_owner(self) -> User | None:
        """
        Получить владельца дерева.

        Returns:
            User или None, если владелец не найден
        """
        collaborator = self.collaborators.filter(role=CollaboratorRoleEnum.OWNER).first()
        return collaborator.user if collaborator else None

    def user_can_edit(self, user: User) -> bool:
        """
        Проверить, может ли пользователь редактировать дерево.

        Args:
            user: Пользователь для проверки

        Returns:
            bool: True, если пользователь может редактировать
        """
        if user.is_superuser:
            return True
        return self.collaborators.filter(
            user=user,
            role__in=[CollaboratorRoleEnum.OWNER, CollaboratorRoleEnum.EDITOR]
        ).exists()

    def user_can_view(self, user: User) -> bool:
        """
        Проверить, может ли пользователь просматривать дерево.

        Args:
            user: Пользователь для проверки

        Returns:
            bool: True, если пользователь может просматривать
        """
        if self.is_public:
            return True
        if user.is_superuser:
            return True
        return self.collaborators.filter(user=user).exists()

    def get_persons_count(self) -> int:
        """
        Получить количество персон в дереве.

        Returns:
            int: Количество персон
        """
        return self.persons.count()


class Person(models.Model):
    """
    Модель персоны в генеалогическом дереве.

    Уникальность обеспечивается комбинацией (first_name, last_name, tree).
    """
    first_name = models.CharField(
        max_length=100,
        verbose_name='Имя'
    )
    middle_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Отчество'
    )
    last_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Фамилия'
    )
    maiden_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Девичья фамилия',
        help_text='Для замужних женщин'
    )
    birth_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата рождения'
    )
    is_birth_date_approx = models.BooleanField(
        default=False,
        verbose_name='Приблизительная дата рождения'
    )
    death_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата смерти'
    )
    is_death_date_approx = models.BooleanField(
        default=False,
        verbose_name='Приблизительная дата смерти'
    )
    birth_place = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Место рождения'
    )
    death_place = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Место смерти'
    )
    burial_place = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Место захоронения'
    )
    gender = models.CharField(
        max_length=10,
        choices=GenderEnum.choices,
        default=GenderEnum.UNKNOWN,
        verbose_name='Пол'
    )
    culture = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Культура/Национальность'
    )
    photo = models.ImageField(
        upload_to='persons/photos/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Фотография'
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name='Заметки'
    )
    tree = models.ForeignKey(
        Tree,
        on_delete=models.CASCADE,
        related_name='persons',
        verbose_name='Дерево'
    )
    status = models.CharField(
        max_length=20,
        choices=PersonStatusEnum.choices,
        default=PersonStatusEnum.SANDBOX,
        verbose_name='Статус'
    )
    merged_into = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='merged_persons',
        verbose_name='Объединена с'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='updated_persons',
        verbose_name='Кем обновлено'
    )

    # Поля для синхронизации
    sync_version = models.IntegerField(
        default=0,
        verbose_name='Версия синхронизации'
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последняя синхронизация'
    )

    class Meta:
        verbose_name = 'Персона'
        verbose_name_plural = 'Персоны'
        ordering = ['last_name', 'first_name']
        # Уникальность: в рамках одного дерева не может быть двух персон с одинаковым ФИО
        constraints = [
            models.UniqueConstraint(
                fields=['first_name', 'last_name', 'tree'],
                name='unique_person_in_tree'
            )
        ]
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['tree', 'status']),
        ]

    def __str__(self) -> str:
        """Строковое представление персоны."""
        return self.full_name_display

    def get_absolute_url(self) -> str:
        """URL детальной страницы персоны."""
        return reverse('genealogy:person_detail', kwargs={'pk': self.pk})

    @property
    def full_name_display(self) -> str:
        """
        Формирует красивое полное имя для отображения.

        Returns:
            str: Полное имя в формате "Фамилия (Девичья) Имя Отчество"
        """
        parts = []
        if self.maiden_name and self.gender == GenderEnum.FEMALE:
            parts.append(f"{self.last_name} ({self.maiden_name})")
        elif self.last_name:
            parts.append(self.last_name)
        parts.append(self.first_name)
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)

    @property
    def age(self) -> int | None:
        """
        Вычисляет возраст персоны.

        Returns:
            int или None: Возраст или None, если даты отсутствуют
        """
        if not self.birth_date:
            return None

        end_date = self.death_date or timezone.now().date()
        age = end_date.year - self.birth_date.year

        # Корректировка, если день рождения ещё не наступил в этом году
        if (end_date.month, end_date.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1

        return age

    @property
    def is_alive(self) -> bool:
        """
        Проверить, жива ли персона.

        Returns:
            bool: True, если персона жива
        """
        return self.death_date is None

    def get_parents(self) -> models.QuerySet['Person']:
        """
        Получить родителей персоны.

        Returns:
            QuerySet: Родители персоны
        """
        parent_relationships = self.relationships_to.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(
            relationships_from__in=parent_relationships
        )

    def get_children(self) -> models.QuerySet['Person']:
        """
        Получить детей персоны.

        Returns:
            QuerySet: Дети персоны
        """
        child_relationships = self.relationships_from.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(
            relationships_to__in=child_relationships
        )

    def get_siblings(self) -> models.QuerySet['Person']:
        """
        Получить братьев и сестер персоны.

        Returns:
            QuerySet: Братья и сестры персоны
        """
        parents = self.get_parents()
        if not parents.exists():
            return Person.objects.none()

        # Находим всех детей тех же родителей
        siblings = Person.objects.filter(
            tree=self.tree,
            relationships_to__from_person__in=parents,
            relationships_to__relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        ).exclude(pk=self.pk).distinct()

        return siblings


class LifeEvent(models.Model):
    """
    Модель события жизни персоны (хронология).
    """
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='life_events',
        verbose_name='Персона'
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventTypeEnum.choices,
        verbose_name='Тип события'
    )
    event_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата события'
    )
    end_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата окончания'
    )
    is_date_approx = models.BooleanField(
        default=False,
        verbose_name='Приблизительная дата'
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Место'
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Описание'
    )
    related_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='related_events',
        verbose_name='Связанная персона'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_events',
        verbose_name='Кем создано'
    )

    # Поля для синхронизации
    sync_version = models.IntegerField(
        default=0,
        verbose_name='Версия синхронизации'
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последняя синхронизация'
    )

    class Meta:
        verbose_name = 'Событие жизни'
        verbose_name_plural = 'События жизни'
        ordering = ['event_date']
        indexes = [
            models.Index(fields=['person', 'event_date']),
            models.Index(fields=['event_type']),
        ]

    def __str__(self) -> str:
        """Строковое представление события."""
        date_str = self.event_date.strftime('%d.%m.%Y') if self.event_date else 'неизвестно'
        return f"{self.get_event_type_display()} - {date_str}"


class Relationship(models.Model):
    """
    Модель связи между двумя персонами.
    """
    from_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='relationships_from',
        verbose_name='От кого'
    )
    to_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='relationships_to',
        verbose_name='К кому'
    )
    relationship_type = models.CharField(
        max_length=20,
        choices=RelationshipTypeEnum.choices,
        verbose_name='Тип связи'
    )
    start_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата начала'
    )
    end_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата окончания'
    )
    is_current = models.BooleanField(
        default=True,
        verbose_name='Текущая связь'
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Описание'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='created_relationships',
        verbose_name='Кем создано'
    )

    # Поля для синхронизации
    sync_version = models.IntegerField(
        default=0,
        verbose_name='Версия синхронизации'
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последняя синхронизация'
    )

    class Meta:
        verbose_name = 'Родственная связь'
        verbose_name_plural = 'Родственные связи'
        # Не должно быть дубликатов связей
        constraints = [
            models.UniqueConstraint(
                fields=['from_person', 'to_person', 'relationship_type'],
                name='unique_relationship'
            )
        ]
        indexes = [
            models.Index(fields=['from_person', 'to_person']),
            models.Index(fields=['relationship_type']),
        ]

    def __str__(self) -> str:
        """Строковое представление связи."""
        return f"{self.from_person} → {self.to_person} ({self.get_relationship_type_display()})"


class TreeCollaborator(models.Model):
    """
    Модель соавтора дерева (права доступа).
    """
    tree = models.ForeignKey(
        Tree,
        on_delete=models.CASCADE,
        related_name='collaborators',
        verbose_name='Дерево'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tree_collaborations',
        verbose_name='Пользователь'
    )
    role = models.CharField(
        max_length=20,
        choices=CollaboratorRoleEnum.choices,
        default=CollaboratorRoleEnum.VIEWER,
        verbose_name='Роль'
    )
    can_invite = models.BooleanField(
        default=False,
        verbose_name='Может приглашать других'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Соавтор дерева'
        verbose_name_plural = 'Соавторы деревьев'
        # Один пользователь может быть соавтором дерева только один раз
        constraints = [
            models.UniqueConstraint(
                fields=['tree', 'user'],
                name='unique_collaborator_per_tree'
            )
        ]

    def __str__(self) -> str:
        """Строковое представление соавтора."""
        return f"{self.user.username} - {self.tree.name} ({self.get_role_display()})"


class ChangeRequest(models.Model):
    """
    Модель запроса на изменение персоны.
    """
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='change_requests',
        verbose_name='Персона'
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='requested_changes',
        verbose_name='Кем запрошено'
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_change_requests',
        verbose_name='Владелец дерева'
    )
    change_type = models.CharField(
        max_length=50,
        verbose_name='Тип изменения',
        help_text='create/update/delete'
    )
    proposed_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name='Предложенные данные'
    )
    status = models.CharField(
        max_length=20,
        choices=ChangeRequestStatusEnum.choices,
        default=ChangeRequestStatusEnum.PENDING,
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    responded_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Дата ответа'
    )
    response_comment = models.TextField(
        blank=True,
        null=True,
        verbose_name='Комментарий к ответу'
    )

    class Meta:
        verbose_name = 'Запрос на изменение'
        verbose_name_plural = 'Запросы на изменения'
        ordering = ['-created_at']

    def __str__(self) -> str:
        """Строковое представление запроса."""
        return f"Запрос #{self.pk} для {self.person} ({self.get_status_display()})"


class UserProfile(models.Model):
    """
    Расширение модели User для хранения дополнительных данных.

    Связан с встроенной Django User моделью через OneToOneField.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь'
    )
    tier = models.CharField(
        max_length=20,
        choices=UserTierEnum.choices,
        default=UserTierEnum.FREE,
        verbose_name='Тариф'
    )
    tier_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Срок действия тарифа'
    )
    devices_count = models.IntegerField(
        default=1,
        verbose_name='Количество устройств'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self) -> str:
        """Строковое представление профиля."""
        return f"Профиль {self.user.username} ({self.get_tier_display()})"

    def can_add_person(self, tree: Tree) -> bool:
        """
        Проверить, может ли пользователь добавить персону в дерево.

        Args:
            tree: Дерево для проверки

        Returns:
            bool: True, если можно добавить
        """
        from django.conf import settings

        # Проверяем лимит тарифа
        tier_limits = settings.TIER_LIMITS.get(self.tier, {})
        max_persons = tier_limits.get('max_persons_per_tree')

        if max_persons is None:
            return True  # Безлимит

        current_count = tree.get_persons_count()
        return current_count < max_persons