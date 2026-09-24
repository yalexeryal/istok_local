"""
Views (обработчики запросов) приложения genealogy.
"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .forms import (
    ExportForm,
    ImportForm,
    LifeEventForm,
    PersonForm,
    RelationshipForm,
)
from .models import (
    ExportTask,
    LifeEvent,
    Person,
    Relationship,
    Tree,
)
from .services.export_service import ExportService
from .services.import_service import ImportService


# === ПУБЛИЧНЫЕ СТРАНИЦЫ ===

class WelcomeView(TemplateView):
    """Публичная страница приветствия."""
    template_name = 'genealogy/welcome.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('genealogy:tree_list')
        return super().get(request, *args, **kwargs)


class RegisterView(CreateView):
    """Страница регистрации нового пользователя."""
    form_class = UserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('genealogy:tree_list')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('genealogy:tree_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            f'Добро пожаловать, {self.object.username}! Ваш аккаунт успешно создан.'
        )
        return response


# === СТРАНИЦЫ, ТРЕБУЮЩИЕ АВТОРИЗАЦИИ ===

class TreeListView(LoginRequiredMixin, ListView):
    """Список деревьев, доступных пользователю."""
    model = Tree
    template_name = 'genealogy/tree_list.html'
    context_object_name = 'trees'

    def get_queryset(self):
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
    """Детальная страница дерева с визуализацией графа."""
    model = Tree
    template_name = 'genealogy/tree_detail.html'
    context_object_name = 'tree'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этому дереву")
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
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
        elif user.is_superuser:
            context['user_role'] = 'Администратор'
            context['can_edit'] = True
        else:
            context['user_role'] = 'Гость'
            context['can_edit'] = False

        return context


@login_required
def tree_data_api(request, pk):
    """API endpoint для получения данных дерева в JSON формате."""
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
    """Создание новой персоны в дереве."""
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления персон в это дерево")

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        context['action'] = 'Создание'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Персона "{self.object.full_name_display}" успешно создана.'
        )
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование существующей персоны."""
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для редактирования персон в этом дереве")

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        context['action'] = 'Редактирование'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Персона "{self.object.full_name_display}" успешно обновлена.'
        )
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.object.pk})


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление персоны с подтверждением."""
    model = Person
    template_name = 'genealogy/person_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления персон в этом дереве")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        person_name = self.object.full_name_display
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Персона "{person_name}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    """Карточка персоны с полной информацией."""
    model = Person
    template_name = 'genealogy/person_detail.html'
    context_object_name = 'person'

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        if not self.object.tree.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этой персоне")

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        user = self.request.user

        context['tree'] = person.tree
        context['parents'] = person.get_parents()
        context['children'] = person.get_children()
        context['siblings'] = person.get_siblings()
        context['life_events'] = person.life_events.all().order_by('event_date')
        context['can_edit'] = person.tree.user_can_edit(user)

        collaborator = person.tree.collaborators.filter(user=user).first()
        if collaborator:
            context['user_role'] = collaborator.get_role_display()
        elif user.is_superuser:
            context['user_role'] = 'Администратор'
        else:
            context['user_role'] = 'Гость'

        return context


# === VIEWS ДЛЯ РОДСТВЕННЫХ СВЯЗЕЙ ===

class RelationshipCreateView(LoginRequiredMixin, CreateView):
    """Создание родственной связи между двумя персонами."""
    model = Relationship
    form_class = RelationshipForm
    template_name = 'genealogy/relationship_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления связей в это дерево")

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Связь между "{self.object.from_person.full_name_display}" и '
            f'"{self.object.to_person.full_name_display}" успешно создана.'
        )
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class RelationshipDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление родственной связи с подтверждением."""
    model = Relationship
    template_name = 'genealogy/relationship_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.tree = self.object.from_person.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления связей в этом дереве")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        from_name = self.object.from_person.full_name_display
        to_name = self.object.to_person.full_name_display
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Связь между "{from_name}" и "{to_name}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


# === VIEWS ДЛЯ СОБЫТИЙ ЖИЗНИ ===

class LifeEventCreateView(LoginRequiredMixin, CreateView):
    """Создание события жизни для персоны."""
    model = LifeEvent
    form_class = LifeEventForm
    template_name = 'genealogy/life_event_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.person = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        self.tree = self.person.tree

        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления событий в это дерево")

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['person'] = self.person
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = self.person
        context['tree'] = self.tree
        context['action'] = 'Создание'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Событие "{self.object.get_event_type_display()}" успешно добавлено.'
        )
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


class LifeEventUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование события жизни."""
    model = LifeEvent
    form_class = LifeEventForm
    template_name = 'genealogy/life_event_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree

        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для редактирования событий в этом дереве")

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['person'] = self.person
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = self.person
        context['tree'] = self.tree
        context['action'] = 'Редактирование'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Событие "{self.object.get_event_type_display()}" успешно обновлено.'
        )
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


class LifeEventDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление события жизни с подтверждением."""
    model = LifeEvent
    template_name = 'genealogy/life_event_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree

        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления событий в этом дереве")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = self.person
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        event_name = self.object.get_event_type_display()
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Событие "{event_name}" успешно удалено.')
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


# === VIEWS ДЛЯ ЭКСПОРТА И ИМПОРТА ===

class TreeExportView(LoginRequiredMixin, View):
    """Страница настройки и запуска экспорта дерева."""
    template_name = 'genealogy/tree_export.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['pk'])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для экспорта этого дерева")

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = ExportForm(tree=self.tree)
        return render(request, self.template_name, {'form': form, 'tree': self.tree})

    def post(self, request, *args, **kwargs):
        form = ExportForm(request.POST, tree=self.tree)
        if form.is_valid():
            service = ExportService()
            task = service.create_export_task(
                user=request.user,
                tree=self.tree,
                export_type=form.cleaned_data['export_type'],
                export_format=form.cleaned_data['export_format'],
                target_person=form.cleaned_data.get('target_person'),
            )

            try:
                service.execute_export(task)
                messages.success(request, 'Экспорт успешно завершён. Файл готов к скачиванию.')
                return redirect('genealogy:tree_export_result', pk=self.tree.pk, task_pk=task.pk)
            except Exception as e:
                messages.error(request, f'Ошибка при экспорте: {e}')
                return redirect('genealogy:tree_detail', pk=self.tree.pk)

        return render(request, self.template_name, {'form': form, 'tree': self.tree})


class TreeExportResultView(LoginRequiredMixin, DetailView):
    """Страница результата экспорта со ссылкой на скачивание."""
    model = ExportTask
    template_name = 'genealogy/tree_export_result.html'
    context_object_name = 'task'

    def get_queryset(self):
        return ExportTask.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.object.tree
        return context


class TreeImportView(LoginRequiredMixin, View):
    """Страница загрузки файла и запуска импорта."""
    template_name = 'genealogy/tree_import.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = ImportForm(user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = ImportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            service = ImportService()
            task = service.create_import_task(
                user=request.user,
                source_file=request.FILES['source_file'],
                target_tree=form.cleaned_data.get('target_tree'),
            )

            try:
                service.execute_import(task)
                messages.success(
                    request,
                    f'Импорт успешно завершён. '
                    f'Импортировано персон: {task.person_count}, '
                    f'связей: {task.relationship_count}.'
                )
                if task.tree:
                    return redirect('genealogy:tree_detail', pk=task.tree.pk)
                return redirect('genealogy:tree_list')
            except Exception as e:
                messages.error(request, f'Ошибка при импорте: {e}')
                return redirect('genealogy:tree_import')

        return render(request, self.template_name, {'form': form})