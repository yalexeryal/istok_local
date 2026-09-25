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
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms import ExportForm, ImportForm, LifeEventForm, PersonForm, RelationshipForm, TreeCreateForm
from .models import (
    CollaboratorRoleEnum,
    EventTypeEnum,
    ExportTask,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)
from .services.export_service import ExportService
from .services.import_service import ImportService
from .utils.names import decline_lastname, generate_patronymic


class WelcomeView(TemplateView):
    template_name = 'genealogy/welcome.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('genealogy:tree_list')
        return super().get(request, *args, **kwargs)


class RegisterView(CreateView):
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
        messages.success(self.request, f'Добро пожаловать, {self.object.username}! Ваш аккаунт успешно создан.')
        return response


class TreeListView(LoginRequiredMixin, ListView):
    model = Tree
    template_name = 'genealogy/tree_list.html'
    context_object_name = 'trees'

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Tree.objects.all()
        return Tree.objects.filter(Q(collaborators__user=user) | Q(is_public=True)).distinct().annotate(
            persons_count=Count('persons', distinct=True), user_role=Q(collaborators__user=user)).order_by(
            '-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        tree_roles = {}
        for tree in context['trees']:
            collaborator = tree.collaborators.filter(user=user).first()
            tree_roles[tree.pk] = collaborator.get_role_display() if collaborator else (
                'Гость' if tree.is_public else '—')
        context['tree_roles'] = tree_roles
        context['total_trees'] = context['trees'].count()
        return context


class TreeCreateView(LoginRequiredMixin, CreateView):
    model = Tree
    form_class = TreeCreateForm
    template_name = 'genealogy/tree_form.html'
    success_url = reverse_lazy('genealogy:tree_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        TreeCollaborator.objects.create(tree=self.object, user=self.request.user, role=CollaboratorRoleEnum.OWNER)
        messages.success(self.request, f'Дерево "{self.object.name}" успешно создано.')
        return response


class TreeDetailView(LoginRequiredMixin, DetailView):
    model = Tree
    template_name = 'genealogy/tree_detail.html'
    context_object_name = 'tree'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этому дереву")
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.object
        user = self.request.user
        context['persons'] = tree.persons.all().prefetch_related('relationships_from', 'relationships_to',
                                                                 'life_events')
        context['persons_count'] = context['persons'].count()
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
    tree = get_object_or_404(Tree, pk=pk)
    if not tree.user_can_view(request.user):
        return JsonResponse({'error': 'Access denied'}, status=403)
    persons = tree.persons.all()
    nodes = [{'data': {'id': str(p.pk), 'label': p.full_name_display, 'first_name': p.first_name,
                       'last_name': p.last_name or '', 'gender': p.gender,
                       'birth_date': p.birth_date.isoformat() if p.birth_date else None,
                       'death_date': p.death_date.isoformat() if p.death_date else None, 'is_alive': p.is_alive,
                       'age': p.age, 'photo_url': p.photo.url if p.photo else None}} for p in persons]
    edges = []
    for p in persons:
        for rel in p.relationships_from.all():
            edges.append({'data': {'id': f"{rel.from_person_id}-{rel.to_person_id}-{rel.relationship_type}",
                                   'source': str(rel.from_person_id), 'target': str(rel.to_person_id),
                                   'relationship_type': rel.relationship_type,
                                   'label': rel.get_relationship_type_display()}})
    return JsonResponse(
        {'tree': {'id': tree.pk, 'name': tree.name, 'description': tree.description}, 'nodes': nodes, 'edges': edges})


def _get_current_spouse(person: Person) -> Person | None:
    """Возвращает текущего супруга персоны по приоритету."""
    spouse_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True) |
        Q(to_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True)
    ).first()

    if spouse_rel:
        return spouse_rel.to_person if spouse_rel.from_person == person else spouse_rel.from_person

    fiance_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.FIANCE) |
        Q(to_person=person, relationship_type=RelationshipTypeEnum.FIANCE)
    ).first()

    if fiance_rel:
        return fiance_rel.to_person if fiance_rel.from_person == person else fiance_rel.from_person

    return None


class PersonCreateView(LoginRequiredMixin, CreateView):
    """Создание новой персоны с поддержкой контекстных параметров."""
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления персон в это дерево")

        # Контекстные параметры
        self.parent1_id = request.GET.get('parent1_id')
        self.relation = request.GET.get('relation')  # son, daughter, adopted_son, adopted_daughter, father, mother
        self.spouse_of_id = request.GET.get('spouse_of')
        self.child_id = request.GET.get('child_id')

        # Загружаем связанные персоны
        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None
        self.spouse_of = Person.objects.filter(pk=self.spouse_of_id).first() if self.spouse_of_id else None
        self.child = Person.objects.filter(pk=self.child_id).first() if self.child_id else None

        # Определяем отца и мать для режима создания ребенка
        self.father = None
        self.mother = None

        if self.parent1 and self.relation in ['son', 'daughter', 'adopted_son', 'adopted_daughter']:
            if self.parent1.gender == 'male':
                self.father = self.parent1
                self.mother = _get_current_spouse(self.parent1)
            else:
                self.mother = self.parent1
                # Пытаемся найти отца как текущего супруга матери
                self.father = _get_current_spouse(self.parent1)

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Предзаполняем форму на основе контекста."""
        initial = super().get_initial()

        # Создание ребенка
        if self.parent1 and self.relation in ['son', 'daughter', 'adopted_son', 'adopted_daughter']:
            is_biological = self.relation in ['son', 'daughter']
            is_male = self.relation in ['son', 'adopted_son']

            initial['gender'] = 'male' if is_male else 'female'
            initial['father'] = self.father.pk if self.father else None
            initial['mother'] = self.mother.pk if self.mother else None

            # Для биологических детей автозаполняем фамилию и отчество
            if is_biological and self.father:
                # Фамилия от отца (склоняем по полу)
                if self.father.last_name:
                    initial['last_name'] = decline_lastname(self.father.last_name, 'male' if is_male else 'female',
                                                            self.father.culture or 'ru')

                # Отчество генерируется от имени отца
                if self.father.first_name:
                    culture = self.father.culture or 'ru'
                    patronymic = generate_patronymic(self.father.first_name, 'male' if is_male else 'female', culture)
                    if patronymic:
                        initial['middle_name'] = patronymic

        # Создание супруга
        elif self.spouse_of:
            if self.spouse_of.gender == 'male':
                initial['gender'] = 'female'
            elif self.spouse_of.gender == 'female':
                initial['gender'] = 'male'

        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'] = self.tree
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree

        # Определяем заголовок формы и контекст
        if self.parent1 and self.relation in ['son', 'daughter', 'adopted_son', 'adopted_daughter']:
            relation_labels = {
                'son': 'сына',
                'daughter': 'дочери',
                'adopted_son': 'приемного сына',
                'adopted_daughter': 'приемную дочь',
            }
            context['action'] = f'Создание карточки {relation_labels[self.relation]}'
            context['parent1'] = self.parent1
            context['father'] = self.father
            context['mother'] = self.mother
            context['form_mode'] = 'child'
        elif self.parent1 and self.relation == 'father':
            context['action'] = 'Создание карточки отца'
            context['child'] = self.parent1
            context['form_mode'] = 'father'
        elif self.parent1 and self.relation == 'mother':
            context['action'] = 'Создание карточки матери'
            context['child'] = self.parent1
            context['form_mode'] = 'mother'
        elif self.spouse_of:
            context['action'] = 'Создание карточки супруга/супруги'
            context['spouse_of'] = self.spouse_of
            context['form_mode'] = 'spouse'
        elif self.child:
            context['action'] = 'Создание карточки родителя'
            context['child'] = self.child
            context['form_mode'] = 'parent'
        else:
            context['action'] = 'Создание'
            context['form_mode'] = 'default'

        return context

    def form_valid(self, form):
        # Проверяем наличие дубликатов
        if form.duplicates_found and not self.request.POST.get('force_create'):
            # Возвращаем форму с предупреждением о дублях
            context = self.get_context_data(form=form)
            context['duplicates_found'] = form.duplicates_found
            return self.render_to_response(self.get_template_names(), context)

        response = super().form_valid(form)
        person = self.object

        # Режим: создание ребенка
        if self.parent1 and self.relation in ['son', 'daughter', 'adopted_son', 'adopted_daughter']:
            is_biological = self.relation in ['son', 'daughter']
            rel_type = RelationshipTypeEnum.BIOLOGICAL_PARENT if is_biological else RelationshipTypeEnum.ADOPTIVE_PARENT

            # Связь parent1 → child
            Relationship.objects.get_or_create(
                from_person=self.parent1,
                to_person=person,
                relationship_type=rel_type,
                defaults={'created_by': self.request.user}
            )

            # Связь второго родителя → child (если указан в форме)
            father = form.cleaned_data.get('father')
            mother = form.cleaned_data.get('mother')

            for parent in [father, mother]:
                if parent and parent != self.parent1:
                    Relationship.objects.get_or_create(
                        from_person=parent,
                        to_person=person,
                        relationship_type=rel_type,
                        defaults={'created_by': self.request.user}
                    )

            # Создаем событие "Рождение ребенка" у родителей
            if person.birth_date:
                all_parents = [self.parent1]
                if father and father != self.parent1:
                    all_parents.append(father)
                if mother and mother != self.parent1:
                    all_parents.append(mother)

                for parent in all_parents:
                    LifeEvent.objects.get_or_create(
                        person=parent,
                        event_type=EventTypeEnum.BIRTH_OF_CHILD,
                        event_date=person.birth_date,
                        related_person=person,
                        defaults={
                            'location': person.birth_place,
                            'description': f'Рождение {"сына" if person.gender == "male" else "дочери"}: {person.full_name_display}',
                            'created_by': self.request.user
                        }
                    )

            messages.success(self.request, f'Ребенок "{person.full_name_display}" успешно создан.')

        # Режим: создание супруга
        elif self.spouse_of:
            marriage_date = self.request.POST.get('marriage_date')
            marriage_place = self.request.POST.get('marriage_place')

            # Создаем связь с датой брака (если указана)
            Relationship.objects.get_or_create(
                from_person=self.spouse_of,
                to_person=person,
                relationship_type=RelationshipTypeEnum.SPOUSE,
                defaults={
                    'created_by': self.request.user,
                    'is_current': True,
                    'start_date': marriage_date or None,
                }
            )

            # Если указана дата брака — создаем событие у обоих супругов
            if marriage_date:
                for spouse in [self.spouse_of, person]:
                    LifeEvent.objects.get_or_create(
                        person=spouse,
                        event_type=EventTypeEnum.MARRIAGE,
                        event_date=marriage_date,
                        related_person=(person if spouse == self.spouse_of else self.spouse_of),
                        defaults={
                            'location': marriage_place,
                            'created_by': self.request.user
                        }
                    )

            messages.success(self.request, f'Супруг(а) "{person.full_name_display}" успешно создан(а).')

        # Режим: создание родителя
        elif self.parent1 and self.relation in ['father', 'mother']:
            Relationship.objects.get_or_create(
                from_person=person,
                to_person=self.parent1,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={'created_by': self.request.user}
            )
            messages.success(self.request, f'Родитель "{person.full_name_display}" успешно создан.')

        elif self.child:
            Relationship.objects.get_or_create(
                from_person=person,
                to_person=self.child,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={'created_by': self.request.user}
            )
            messages.success(self.request, f'Родитель "{person.full_name_display}" успешно создан.')

        else:
            messages.success(self.request, f'Персона "{person.full_name_display}" успешно создана.')

        return response

    def get_success_url(self):
        if self.parent1:
            return reverse('genealogy:person_detail', kwargs={'pk': self.parent1.pk})
        elif self.spouse_of:
            return reverse('genealogy:person_detail', kwargs={'pk': self.spouse_of.pk})
        elif self.child:
            return reverse('genealogy:person_detail', kwargs={'pk': self.child.pk})
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    model = Person
    form_class = PersonForm
    template_name = 'genealogy/person_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для редактирования персон в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'], kwargs['user'] = self.tree, self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        context['action'] = 'Редактирование'
        context['form_mode'] = 'edit'
        return context

    def form_valid(self, form):
        # Проверяем дубликаты
        if form.duplicates_found and not self.request.POST.get('force_create'):
            context = self.get_context_data(form=form)
            context['duplicates_found'] = form.duplicates_found
            return self.render_to_response(self.get_template_names(), context)

        response = super().form_valid(form)
        messages.success(self.request, f'Персона "{self.object.full_name_display}" успешно обновлена.')
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.object.pk})


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    model = Person
    template_name = 'genealogy/person_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для удаления персон в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Персона "{self.object.full_name_display}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    template_name = 'genealogy/person_detail.html'
    context_object_name = 'person'

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        if not self.object.tree.user_can_view(request.user): return HttpResponseForbidden(
            "У вас нет доступа к этой персоне")
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        user = self.request.user

        context['tree'] = person.tree
        context['combined_timeline'] = person.get_combined_timeline()
        context['can_edit'] = person.tree.user_can_edit(user)

        collaborator = person.tree.collaborators.filter(user=user).first()
        context['user_role'] = collaborator.get_role_display() if collaborator else (
            'Администратор' if user.is_superuser else 'Гость')

        # Определяем родителей для отображения
        parents = person.get_parents()
        context['father'] = next((p for p in parents if p.gender == 'male'), None)
        context['mother'] = next((p for p in parents if p.gender == 'female'), None)

        # Формируем список ближайших родственников
        close_relatives = []

        # Родители
        for p in parents:
            rel = Relationship.objects.filter(
                from_person=p, to_person=person,
                relationship_type__in=[RelationshipTypeEnum.BIOLOGICAL_PARENT, RelationshipTypeEnum.ADOPTIVE_PARENT,
                                       RelationshipTypeEnum.STEP_PARENT]
            ).first()
            if rel:
                if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                    rel_type = "Отец (Родной)" if p.gender == 'male' else "Мать (Родная)"
                elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                    rel_type = "Отец (Приемный)" if p.gender == 'male' else "Мать (Приемная)"
                else:
                    rel_type = "Отчим" if p.gender == 'male' else "Мачеха"
                close_relatives.append({'person': p, 'relation': rel_type})

        # Дети
        for c in person.get_children():
            rel = Relationship.objects.filter(
                from_person=person, to_person=c,
                relationship_type__in=[RelationshipTypeEnum.BIOLOGICAL_PARENT, RelationshipTypeEnum.ADOPTIVE_PARENT,
                                       RelationshipTypeEnum.STEP_PARENT]
            ).first()
            if rel:
                if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                    rel_type = "Сын (Родной)" if c.gender == 'male' else "Дочь (Родная)"
                elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                    rel_type = "Сын (Приемный)" if c.gender == 'male' else "Дочь (Приемная)"
                else:
                    rel_type = "Пасынок" if c.gender == 'male' else "Падчерица"
                close_relatives.append({'person': c, 'relation': rel_type})

        # Супруги/Партнеры
        for spouse_info in person.get_spouses():
            partner = spouse_info['person']
            rel_type_rel = spouse_info['relationship']
            if spouse_info['type'] == RelationshipTypeEnum.SPOUSE:
                rel_type = "Партнер (Официальный брак)"
            elif spouse_info['type'] == RelationshipTypeEnum.EX_SPOUSE:
                rel_type = "Бывший партнер"
            else:
                rel_type = "Жених/Невеста"
            close_relatives.append({'person': partner, 'relation': rel_type})

        context['close_relatives'] = close_relatives
        return context


class RelationshipCreateView(LoginRequiredMixin, CreateView):
    model = Relationship
    form_class = RelationshipForm
    template_name = 'genealogy/relationship_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.tree = get_object_or_404(Tree, pk=self.kwargs['tree_pk'])
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для добавления связей в это дерево")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['tree'], kwargs['user'] = self.tree, self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request,
                         f'Связь между "{self.object.from_person.full_name_display}" и "{self.object.to_person.full_name_display}" успешно создана.')
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class RelationshipDeleteView(LoginRequiredMixin, DeleteView):
    model = Relationship
    template_name = 'genealogy/relationship_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.from_person.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для удаления связей в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(request,
                         f'Связь между "{self.object.from_person.full_name_display}" и "{self.object.to_person.full_name_display}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse('genealogy:tree_detail', kwargs={'pk': self.tree.pk})


class LifeEventCreateView(LoginRequiredMixin, CreateView):
    model = LifeEvent
    form_class = LifeEventForm
    template_name = 'genealogy/life_event_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.person = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для добавления событий в это дерево")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['person'], kwargs['tree'], kwargs['user'] = self.person, self.tree, self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'], context['tree'], context['action'] = self.person, self.tree, 'Создание'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Событие "{self.object.get_event_type_display()}" успешно добавлено.')
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


class LifeEventUpdateView(LoginRequiredMixin, UpdateView):
    model = LifeEvent
    form_class = LifeEventForm
    template_name = 'genealogy/life_event_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для редактирования событий в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['person'], kwargs['tree'], kwargs['user'] = self.person, self.tree, self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'], context['tree'], context['action'] = self.person, self.tree, 'Редактирование'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Событие "{self.object.get_event_type_display()}" успешно обновлено.')
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


class LifeEventDeleteView(LoginRequiredMixin, DeleteView):
    model = LifeEvent
    template_name = 'genealogy/life_event_confirm_delete.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для удаления событий в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'], context['tree'] = self.person, self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Событие "{self.object.get_event_type_display()}" успешно удалено.')
        return response

    def get_success_url(self):
        return reverse('genealogy:person_detail', kwargs={'pk': self.person.pk})


class TreeExportView(LoginRequiredMixin, View):
    template_name = 'genealogy/tree_export.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        self.tree = get_object_or_404(Tree, pk=self.kwargs['pk'])
        if not self.tree.user_can_edit(request.user): return HttpResponseForbidden(
            "У вас нет прав для экспорта этого дерева")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {'form': ExportForm(tree=self.tree), 'tree': self.tree})

    def post(self, request, *args, **kwargs):
        form = ExportForm(request.POST, tree=self.tree)
        if form.is_valid():
            service = ExportService()
            task = service.create_export_task(user=request.user, tree=self.tree,
                                              export_type=form.cleaned_data['export_type'],
                                              export_format=form.cleaned_data['export_format'],
                                              target_person=form.cleaned_data.get('target_person'))
            try:
                service.execute_export(task)
                messages.success(request, 'Экспорт успешно завершён. Файл готов к скачиванию.')
                return redirect('genealogy:tree_export_result', pk=self.tree.pk, task_pk=task.pk)
            except Exception as e:
                messages.error(request, f'Ошибка при экспорте: {e}')
                return redirect('genealogy:tree_detail', pk=self.tree.pk)
        return render(request, self.template_name, {'form': form, 'tree': self.tree})


class TreeExportResultView(LoginRequiredMixin, DetailView):
    model = ExportTask
    template_name = 'genealogy/tree_export_result.html'
    context_object_name = 'task'

    def get_queryset(self): return ExportTask.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tree'] = self.object.tree
        return context


class TreeImportView(LoginRequiredMixin, View):
    template_name = 'genealogy/tree_import.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated: return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {'form': ImportForm(user=request.user)})

    def post(self, request, *args, **kwargs):
        form = ImportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            service = ImportService()
            task = service.create_import_task(user=request.user, source_file=request.FILES['source_file'],
                                              target_tree=form.cleaned_data.get('target_tree'))
            try:
                service.execute_import(task)
                messages.success(request,
                                 f'Импорт успешно завершён. Импортировано персон: {task.person_count}, связей: {task.relationship_count}.')
                return redirect('genealogy:tree_detail', pk=task.tree.pk) if task.tree else redirect(
                    'genealogy:tree_list')
            except Exception as e:
                messages.error(request, f'Ошибка при импорте: {e}')
                return redirect('genealogy:tree_import')
        return render(request, self.template_name, {'form': form})