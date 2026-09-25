"""
Views для работы с персонами.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from genealogy.forms import PersonForm
from genealogy.models import (
    EventTypeEnum,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
)
from genealogy.utils.names import decline_lastname, generate_patronymic


def _get_current_spouse(person: Person) -> Person | None:
    """Возвращает текущего супруга персоны по приоритету."""
    spouse_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True)
        | Q(to_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True)
    ).first()

    if spouse_rel:
        return spouse_rel.to_person if spouse_rel.from_person == person else spouse_rel.from_person

    fiance_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.FIANCE)
        | Q(to_person=person, relationship_type=RelationshipTypeEnum.FIANCE)
    ).first()

    if fiance_rel:
        return fiance_rel.to_person if fiance_rel.from_person == person else fiance_rel.from_person

    return None


class PersonCreateView(LoginRequiredMixin, CreateView):
    """Создание новой персоны с поддержкой контекстных параметров."""

    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs["tree_pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления персон в это дерево")

        # Контекстные параметры
        self.parent1_id = request.GET.get("parent1_id")
        self.relation = request.GET.get("relation")  # son, daughter, adopted_son, adopted_daughter, father, mother
        self.spouse_of_id = request.GET.get("spouse_of")
        self.child_id = request.GET.get("child_id")

        # Загружаем связанные персоны
        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None
        self.spouse_of = Person.objects.filter(pk=self.spouse_of_id).first() if self.spouse_of_id else None
        self.child = Person.objects.filter(pk=self.child_id).first() if self.child_id else None

        # Определяем отца и мать для режима создания ребенка
        self.father = None
        self.mother = None

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            if self.parent1.gender == "male":
                self.father = self.parent1
                self.mother = _get_current_spouse(self.parent1)
            else:
                self.mother = self.parent1
                self.father = _get_current_spouse(self.parent1)

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Предзаполняем форму на основе контекста."""
        initial = super().get_initial()

        # Создание ребенка
        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            is_biological = self.relation in ["son", "daughter"]
            is_male = self.relation in ["son", "adopted_son"]

            initial["gender"] = "male" if is_male else "female"
            initial["father"] = self.father.pk if self.father else None
            initial["mother"] = self.mother.pk if self.mother else None

            # Для биологических детей автозаполняем фамилию и отчество
            if is_biological and self.father:
                if self.father.last_name:
                    initial["last_name"] = decline_lastname(
                        self.father.last_name,
                        "male" if is_male else "female",
                        self.father.culture or "ru",
                    )

                if self.father.first_name:
                    culture = self.father.culture or "ru"
                    patronymic = generate_patronymic(
                        self.father.first_name,
                        "male" if is_male else "female",
                        culture,
                    )
                    if patronymic:
                        initial["middle_name"] = patronymic

        # Создание супруга
        elif self.spouse_of:
            if self.spouse_of.gender == "male":
                initial["gender"] = "female"
            elif self.spouse_of.gender == "female":
                initial["gender"] = "male"

        # Создание родителя
        elif self.parent1 and self.relation in ["father", "mother"]:
            initial["gender"] = "male" if self.relation == "father" else "female"

        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            relation_labels = {
                "son": "сына",
                "daughter": "дочери",
                "adopted_son": "приемного сына",
                "adopted_daughter": "приемную дочь",
            }
            context["action"] = f"Создание карточки {relation_labels[self.relation]}"
            context["parent1"] = self.parent1
            context["father"] = self.father
            context["mother"] = self.mother
            context["form_mode"] = "child"
        elif self.parent1 and self.relation in ["father", "mother"]:
            context["action"] = "Создание карточки отца" if self.relation == "father" else "Создание карточки матери"
            context["child"] = self.parent1
            context["form_mode"] = "parent_of_child"
        elif self.spouse_of:
            context["action"] = "Создание карточки супруга/супруги"
            context["spouse_of"] = self.spouse_of
            context["form_mode"] = "spouse"
        elif self.child:
            context["action"] = "Создание карточки родителя"
            context["child"] = self.child
            context["form_mode"] = "parent"
        else:
            context["action"] = "Создание"
            context["form_mode"] = "default"

        return context

    def form_valid(self, form):
        # Проверяем наличие дубликатов
        if form.duplicates_found and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(self.get_template_names(), context)

        response = super().form_valid(form)
        person = self.object

        # Режим: создание ребенка
        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            is_biological = self.relation in ["son", "daughter"]
            rel_type = RelationshipTypeEnum.BIOLOGICAL_PARENT if is_biological else RelationshipTypeEnum.ADOPTIVE_PARENT

            Relationship.objects.get_or_create(
                from_person=self.parent1,
                to_person=person,
                relationship_type=rel_type,
                defaults={"created_by": self.request.user},
            )

            father = form.cleaned_data.get("father")
            mother = form.cleaned_data.get("mother")

            for parent in [father, mother]:
                if parent and parent != self.parent1:
                    Relationship.objects.get_or_create(
                        from_person=parent,
                        to_person=person,
                        relationship_type=rel_type,
                        defaults={"created_by": self.request.user},
                    )

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
                            "location": person.birth_place,
                            "description": f"Рождение {'сына' if person.gender == 'male' else 'дочери'}: {person.full_name_display}",
                            "created_by": self.request.user,
                        },
                    )

            messages.success(self.request, f'Ребенок "{person.full_name_display}" успешно создан.')

        # Режим: создание супруга
        elif self.spouse_of:
            marriage_date = self.request.POST.get("marriage_date")
            marriage_place = self.request.POST.get("marriage_place")

            Relationship.objects.get_or_create(
                from_person=self.spouse_of,
                to_person=person,
                relationship_type=RelationshipTypeEnum.SPOUSE,
                defaults={
                    "created_by": self.request.user,
                    "is_current": True,
                    "start_date": marriage_date or None,
                },
            )

            if marriage_date:
                for spouse in [self.spouse_of, person]:
                    LifeEvent.objects.get_or_create(
                        person=spouse,
                        event_type=EventTypeEnum.MARRIAGE,
                        event_date=marriage_date,
                        related_person=(person if spouse == self.spouse_of else self.spouse_of),
                        defaults={
                            "location": marriage_place,
                            "created_by": self.request.user,
                        },
                    )

            messages.success(self.request, f'Супруг(а) "{person.full_name_display}" успешно создан(а).')

        # Режим: создание родителя
        elif self.parent1 and self.relation in ["father", "mother"]:
            Relationship.objects.get_or_create(
                from_person=person,
                to_person=self.parent1,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={"created_by": self.request.user},
            )
            messages.success(self.request, f'Родитель "{person.full_name_display}" успешно создан.')

        elif self.child:
            Relationship.objects.get_or_create(
                from_person=person,
                to_person=self.child,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={"created_by": self.request.user},
            )
            messages.success(self.request, f'Родитель "{person.full_name_display}" успешно создан.')

        else:
            messages.success(self.request, f'Персона "{person.full_name_display}" успешно создана.')

        return response

    def get_success_url(self):
        if self.parent1:
            return reverse("genealogy:person_detail", kwargs={"pk": self.parent1.pk})
        elif self.spouse_of:
            return reverse("genealogy:person_detail", kwargs={"pk": self.spouse_of.pk})
        elif self.child:
            return reverse("genealogy:person_detail", kwargs={"pk": self.child.pk})
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование существующей персоны."""

    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

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
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree
        context["action"] = "Редактирование"
        context["form_mode"] = "edit"
        return context

    def form_valid(self, form):
        if form.duplicates_found and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(self.get_template_names(), context)

        response = super().form_valid(form)
        messages.success(self.request, f'Персона "{self.object.full_name_display}" успешно обновлена.')
        return response

    def get_success_url(self):
        return reverse("genealogy:person_detail", kwargs={"pk": self.object.pk})


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление персоны с подтверждением."""

    model = Person
    template_name = "genealogy/person_confirm_delete.html"

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
        context["tree"] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Персона "{self.object.full_name_display}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    """Карточка персоны с полной информацией."""

    model = Person
    template_name = "genealogy/person_detail.html"
    context_object_name = "person"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        if not self.object.tree.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этой персоне")
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        user = self.request.user

        context["tree"] = person.tree
        context["combined_timeline"] = person.get_combined_timeline()
        context["can_edit"] = person.tree.user_can_edit(user)

        collaborator = person.tree.collaborators.filter(user=user).first()
        context["user_role"] = (
            collaborator.get_role_display() if collaborator else ("Администратор" if user.is_superuser else "Гость")
        )

        # Определяем родителей для отображения
        parents = person.get_parents()
        context["father"] = next((p for p in parents if p.gender == "male"), None)
        context["mother"] = next((p for p in parents if p.gender == "female"), None)

        # Формируем список ближайших родственников
        close_relatives = []

        # Родители
        for p in parents:
            rel = Relationship.objects.filter(
                from_person=p,
                to_person=person,
                relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ],
            ).first()
            if rel:
                if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                    rel_type = "Отец (Родной)" if p.gender == "male" else "Мать (Родная)"
                elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                    rel_type = "Отец (Приемный)" if p.gender == "male" else "Мать (Приемная)"
                else:
                    rel_type = "Отчим" if p.gender == "male" else "Мачеха"
                close_relatives.append({"person": p, "relation": rel_type})

        # Дети
        for c in person.get_children():
            rel = Relationship.objects.filter(
                from_person=person,
                to_person=c,
                relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ],
            ).first()
            if rel:
                if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                    rel_type = "Сын (Родной)" if c.gender == "male" else "Дочь (Родная)"
                elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                    rel_type = "Сын (Приемный)" if c.gender == "male" else "Дочь (Приемная)"
                else:
                    rel_type = "Пасынок" if c.gender == "male" else "Падчерица"
                close_relatives.append({"person": c, "relation": rel_type})

        # Супруги/Партнеры
        for spouse_info in person.get_spouses():
            partner = spouse_info["person"]
            if spouse_info["type"] == RelationshipTypeEnum.SPOUSE:
                rel_type = "Партнер (Официальный брак)"
            elif spouse_info["type"] == RelationshipTypeEnum.EX_SPOUSE:
                rel_type = "Бывший партнер"
            else:
                rel_type = "Жених/Невеста"
            close_relatives.append({"person": partner, "relation": rel_type})

        context["close_relatives"] = close_relatives
        return context
