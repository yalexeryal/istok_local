"""
Views (обработчики запросов) приложения genealogy.

Включает:
- TreeListView — список деревьев пользователя
- TreeDetailView — детальная страница дерева с визуализацией
- tree_data_api — API для получения данных дерева в JSON
- PersonCreateView — создание персоны
- PersonUpdateView — редактирование персоны
- PersonDeleteView — удаление персоны
- PersonDetailView — карточка персоны
- RelationshipCreateView — создание родственной связи
- RelationshipDeleteView — удаление родственной связи
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import PersonForm, RelationshipForm
from .models import Person, Relationship, Tree


# === VIEWS ДЛЯ ДЕРЕВЬЕВ ===

class TreeListView(LoginRequiredMixin, ListView):
    """
    Главная страница: список деревьев, доступных пользователю.
    """
    model = Tree
    template_name = 'genealogy/tree_list.html'
    context_object_name = 'trees'

    def get_queryset(self):
        """Возвращает деревья, доступные текущему пользователю."""
        user = self.request.user

        if user.is_superuser:
            queryset = Tree.objects.all()
        else:
            queryset = Tree.objects.filter(
                Q(collaborators__user=user) | Q(is_public=True)
            ).distinct()

        return queryset.annotate(
            persons_count=Count('persons', distinct=True),
            user_role=Q(collaborators__user=user)
        ).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        """Добавляем дополнительную информацию в контекст."""
        context = super().get_context_data(**kwargs)

        user = self.request.user
        trees = context['trees']

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
    """
    model = Tree
    template_name = 'genealogy/tree_detail.html'
    context_object_name = 'tree'

    def get(self, request, *args, **kwargs):
        """Переопределяем GET для проверки прав ДО рендеринга шаблона."""
        self.object = self.get_object()

        if not self.object.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этому дереву")

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        """Добавляем дополнительную информацию в контекст."""
        context = super().get_context_data(**kwargs)
        tree = self.object
        user = self.request.user

        persons = tree.persons.all().prefetch_related(
            'relationships_from',
            'relationships_to',
            'life_events'
        )

        context['persons'] = persons
        context['persons_count'] = persons.count()

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
    """
    tree = get_object_or_404(Tree, pk=pk)

    if not tree.user_can_view(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)

    persons = tree.persons.all()

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

    edges = []
    for person in persons:
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


# === VIEWS ДЛЯ ПЕРСОН (CRUD) ===

class PersonCreateView(LoginRequiredMixin, CreateView):
    """
    Создание новой персоны в дереве.

    Доступ:
    - Только авторизованные пользователи
    - Только OWNER и EDITOR дерева
    """
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])

        # Теперь request.user гарантированно User, можно проверять права
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden(
                "У вас нет прав для добавления персон в это дерево"
            )

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Передаём tree и user в форму."""
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Добавляем дерево в контекст."""
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        context['action'] = 'Создание'
        return context

    def form_valid(self, form):
        """При успешном создании перенаправляем на страницу дерева."""
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Персона "{self.object.full_name_display}" успешно создана.'
        )
        return response

    def get_success_url(self):
        """Перенаправляем на страницу дерева."""
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    """
    Редактирование существующей персоны.

    Доступ:
    - Только авторизованные пользователи
    - Только OWNER и EDITOR дерева, к которому принадлежит персона
    """
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву персоны.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.tree

        # Теперь request.user гарантированно User, можно проверять права
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden(
                "У вас нет прав для редактирования персон в этом дереве"
            )

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Передаём tree и user в форму."""
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Добавляем дерево в контекст."""
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        context['action'] = 'Редактирование'
        return context

    def form_valid(self, form):
        """При успешном редактировании показываем сообщение."""
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Персона "{self.object.full_name_display}" успешно обновлена.'
        )
        return response

    def get_success_url(self):
        """Перенаправляем на страницу персоны."""
        return reverse('genealogy:person_detail', kwargs={'pk': self.object.pk})


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    """
    Удаление персоны с подтверждением.

    Доступ:
    - Только авторизованные пользователи
    - Только OWNER и EDITOR дерева
    """
    model = Person
    template_name = 'genealogy/person_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву персоны.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.tree

        # Теперь request.user гарантированно User, можно проверять права
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden(
                "У вас нет прав для удаления персон в этом дереве"
            )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Добавляем дерево в контекст."""
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        """При удалении показываем сообщение."""
        self.object = self.get_object()
        person_name = self.object.full_name_display
        response = super().delete(request, *args, **kwargs)
        messages.success(
            request,
            f'Персона "{person_name}" успешно удалена.'
        )
        return response

    def get_success_url(self):
        """Перенаправляем на страницу дерева."""
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    """
    Карточка персоны с полной информацией.

    Показывает:
    - Основную информацию
    - События жизни
    - Родственные связи
    - Родителей, детей, братьев/сестер
    """
    model = Person
    template_name = 'genealogy/person_detail.html'
    context_object_name = 'person'

    def get(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву персоны.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()

        # Теперь request.user гарантированно User, можно проверять права
        if not self.object.tree.user_can_view(request.user):
            return HttpResponseForbidden(
                "У вас нет доступа к этой персоне"
            )

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        """Добавляем связанную информацию в контекст."""
        context = super().get_context_data(**kwargs)
        person = self.object
        user = self.request.user

        context['tree'] = person.tree
        context['parents'] = person.get_parents()
        context['children'] = person.get_children()
        context['siblings'] = person.get_siblings()
        context['life_events'] = person.life_events.all().order_by('event_date')
        context['can_edit'] = person.tree.user_can_edit(user)

        # Роль пользователя
        collaborator = person.tree.collaborators.filter(user=user).first()
        if collaborator:
            context['user_role'] = collaborator.get_role_display()
        else:
            context['user_role'] = 'Гость'

        return context


# === VIEWS ДЛЯ РОДСТВЕННЫХ СВЯЗЕЙ ===

class RelationshipCreateView(LoginRequiredMixin, CreateView):
    """
    Создание родственной связи между двумя персонами.

    Доступ:
    - Только авторизованные пользователи
    - Только OWNER и EDITOR дерева
    """
    model = Relationship
    form_class = RelationshipForm
    template_name = 'genealogy/relationship_form.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])

        # Теперь request.user гарантированно User, можно проверять права
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden(
                "У вас нет прав для добавления связей в это дерево"
            )

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Передаём tree и user в форму."""
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Добавляем дерево в контекст."""
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def form_valid(self, form):
        """При успешном создании перенаправляем на страницу дерева."""
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Связь между "{self.object.from_person.full_name_display}" и '
            f'"{self.object.to_person.full_name_display}" успешно создана.'
        )
        return response

    def get_success_url(self):
        """Перенаправляем на страницу дерева."""
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class RelationshipDeleteView(LoginRequiredMixin, DeleteView):
    """
    Удаление родственной связи с подтверждением.

    Доступ:
    - Только авторизованные пользователи
    - Только OWNER и EDITOR дерева
    """
    model = Relationship
    template_name = 'genealogy/relationship_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Проверяем аутентификацию и права доступа к дереву связи.

        Важно: сначала проверяем is_authenticated, чтобы избежать
        ошибки при использовании AnonymousUser в запросах к БД.
        """
        # Сначала проверяем аутентификацию (для AnonymousUser)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.from_person.tree

        # Теперь request.user гарантированно User, можно проверять права
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden(
                "У вас нет прав для удаления связей в этом дереве"
            )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Добавляем дерево в контекст."""
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        """При удалении показываем сообщение."""
        self.object = self.get_object()
        from_name = self.object.from_person.full_name_display
        to_name = self.object.to_person.full_name_display
        response = super().delete(request, *args, **kwargs)
        messages.success(
            request,
            f'Связь между "{from_name}" и "{to_name}" успешно удалена.'
        )
        return response

    def get_success_url(self):
        """Перенаправляем на страницу дерева."""
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})