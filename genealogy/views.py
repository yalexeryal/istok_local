"""
Views (обработчики запросов) приложения genealogy.

Включает:
- TreeListView — список деревьев пользователя
- TreeDetailView — детальная страница дерева с визуализацией
- tree_data_api — API для получения данных дерева в JSON
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from .models import Tree


class TreeListView(LoginRequiredMixin, ListView):
    """
    Главная страница: список деревьев, доступных пользователю.

    Показывает:
    - Деревья, где пользователь является соавтором (любая роль)
    - Публичные деревья (если пользователь вошёл)

    Для каждого дерева отображается:
    - Название
    - Количество персон
    - Роль пользователя
    - Дата последнего обновления
    """
    model = Tree
    template_name = 'genealogy/tree_list.html'
    context_object_name = 'trees'

    def get_queryset(self):
        """
        Возвращает деревья, доступные текущему пользователю.

        Логика:
        1. Деревья, где пользователь — соавтор (любая роль)
        2. Публичные деревья
        3. Для суперпользователя — все деревья

        Оптимизация:
        - Аннотируем количество персон (чтобы не делать запрос для каждого дерева)
        - Аннотируем роль пользователя
        """
        user = self.request.user

        # Суперпользователь видит все деревья
        if user.is_superuser:
            queryset = Tree.objects.all()
        else:
            # Обычный пользователь видит свои деревья + публичные
            queryset = Tree.objects.filter(
                Q(collaborators__user=user) | Q(is_public=True)
            ).distinct()

        # Аннотируем количество персон и роль пользователя
        return queryset.annotate(
            persons_count=Count('persons', distinct=True),
            user_role=Q(collaborators__user=user)
        ).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        """Добавляем дополнительную информацию в контекст."""
        context = super().get_context_data(**kwargs)

        # Получаем роли пользователя для каждого дерева
        user = self.request.user
        trees = context['trees']

        # Для каждого дерева определяем роль пользователя
        tree_roles = {}
        for tree in trees:
            collaborator = tree.collaborators.filter(user=user).first()
            if collaborator:
                tree_roles[tree.pk] = collaborator.get_role_display()
            elif tree.is_public:
                tree_roles[tree.pk] = 'Гость'
            else:
                tree_roles[tree.pk] = '—'

        context['tree_roles'] = tree_roles
        context['total_trees'] = trees.count()

        return context


class TreeDetailView(LoginRequiredMixin, DetailView):
    """
    Детальная страница дерева с визуализацией графа.

    Показывает:
    - Информацию о дереве
    - Интерактивную визуализацию через Cytoscape.js
    - Список персон

    Проверка прав:
    - Владелец и соавторы — полный доступ
    - Для публичных деревьев — любой авторизованный пользователь
    - Для приватных деревьев без доступа — HTTP 403
    """
    model = Tree
    template_name = 'genealogy/tree_detail.html'
    context_object_name = 'tree'

    def get(self, request, *args, **kwargs):
        """
        Переопределяем GET для проверки прав ДО рендеринга шаблона.

        Это правильный способ вернуть HttpResponseForbidden из DetailView.
        """
        self.object = self.get_object()

        # Проверяем права доступа
        if not self.object.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этому дереву")

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        """Добавляем дополнительную информацию в контекст."""
        context = super().get_context_data(**kwargs)
        tree = self.object
        user = self.request.user

        # Получаем всех персон с их связями
        persons = tree.persons.all().prefetch_related(
            'relationships_from',
            'relationships_to',
            'life_events'
        )

        context['persons'] = persons
        context['persons_count'] = persons.count()

        # Получаем роль пользователя
        collaborator = tree.collaborators.filter(user=user).first()
        if collaborator:
            context['user_role'] = collaborator.get_role_display()
            context['can_edit'] = tree.user_can_edit(user)
        else:
            context['user_role'] = 'Гость'
            context['can_edit'] = False

        return context


@login_required
def tree_data_api(request, pk):
    """
    API endpoint для получения данных дерева в JSON формате.

    Используется Cytoscape.js для визуализации графа.

    Защита:
    - @login_required — только авторизованные пользователи
    - Проверка прав через tree.user_can_view()

    Returns:
        JSON с узлами (nodes) и рёбрами (edges)
    """
    tree = get_object_or_404(Tree, pk=pk)

    # Проверяем права доступа
    if not tree.user_can_view(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    # Получаем всех персон
    persons = tree.persons.all()

    # Формируем узлы (nodes)
    nodes = []
    for person in persons:
        node = {
            'data': {
                'id': str(person.pk),
                'label': person.full_name_display,
                'first_name': person.first_name,
                'last_name': person.last_name or '',
                'gender': person.gender,
                'birth_date': person.birth_date.isoformat() if person.birth_date else None,
                'death_date': person.death_date.isoformat() if person.death_date else None,
                'is_alive': person.is_alive,
                'age': person.age,
                'photo_url': person.photo.url if person.photo else None,
            }
        }
        nodes.append(node)

    # Формируем рёбра (edges)
    edges = []
    for person in persons:
        # Родительские связи
        for rel in person.relationships_from.all():
            edge = {
                'data': {
                    'id': f"{rel.from_person_id}-{rel.to_person_id}-{rel.relationship_type}",
                    'source': str(rel.from_person_id),
                    'target': str(rel.to_person_id),
                    'relationship_type': rel.relationship_type,
                    'label': rel.get_relationship_type_display(),
                }
            }
            edges.append(edge)

    return JsonResponse({
        'tree': {
            'id': tree.pk,
            'name': tree.name,
            'description': tree.description,
        },
        'nodes': nodes,
        'edges': edges,
    })