"""
Views для работы с персонами.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from genealogy.forms import PersonForm
from genealogy.models import (
    EventTypeEnum,
    LifeEvent,
    Person,
    PersonPhoto,
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


RELATION_LABELS = {
    "son": "сын",
    "daughter": "дочь",
    "adopted_son": "приемный сын",
    "adopted_daughter": "приемная дочь",
    "father": "отец",
    "mother": "мать",
    "spouse": "супруг(а)",
}


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

        self.parent1_id = request.GET.get("parent1_id")
        self.relation = request.GET.get("relation")
        self.spouse_of_id = request.GET.get("spouse_of")
        self.child_id = request.GET.get("child_id")

        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None
        self.spouse_of = Person.objects.filter(pk=self.spouse_of_id).first() if self.spouse_of_id else None
        self.child = Person.objects.filter(pk=self.child_id).first() if self.child_id else None

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
        initial = super().get_initial()

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            is_biological = self.relation in ["son", "daughter"]
            is_male = self.relation in ["son", "adopted_son"]

            initial["gender"] = "male" if is_male else "female"
            initial["father"] = self.father.pk if self.father else None
            initial["mother"] = self.mother.pk if self.mother else None

            if is_biological and self.father:
                if self.father.last_name:
                    initial["last_name"] = decline_lastname(
                        self.father.last_name, "male" if is_male else "female", self.father.culture or "ru"
                    )

                if self.father.first_name:
                    culture = self.father.culture or "ru"
                    patronymic = generate_patronymic(self.father.first_name, "male" if is_male else "female", culture)
                    if patronymic:
                        initial["middle_name"] = patronymic

        elif self.spouse_of:
            if self.spouse_of.gender == "male":
                initial["gender"] = "female"
            elif self.spouse_of.gender == "female":
                initial["gender"] = "male"

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
        has_exact_duplicate = form.exact_duplicate is not None
        has_similar_duplicates = len(form.duplicates_found) > 0

        if (has_exact_duplicate or has_similar_duplicates) and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["exact_duplicate"] = form.exact_duplicate
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(context)

        response = super().form_valid(form)
        person = self.object

        # === ЛОГИРОВАНИЕ: создание персоны ===
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

        # ... остальной код без изменений ...

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

        elif self.spouse_of:
            marriage_date = self.request.POST.get("marriage_date")
            marriage_place = self.request.POST.get("marriage_place")

            Relationship.objects.get_or_create(
                from_person=self.spouse_of,
                to_person=person,
                relationship_type=RelationshipTypeEnum.SPOUSE,
                defaults={"created_by": self.request.user, "is_current": True, "start_date": marriage_date or None},
            )

            # Создаём событие брака у обоих супругов.

            # Если дата не указана — всё равно создаём событие (чтобы связь была видна),

            # но без даты. Пользователь сможет добавить дату позже через редактирование.

            for spouse in [self.spouse_of, person]:
                related = person if spouse == self.spouse_of else self.spouse_of

                LifeEvent.objects.get_or_create(
                    person=spouse,
                    event_type=EventTypeEnum.MARRIAGE,
                    event_date=marriage_date or None,
                    related_person=related,
                    defaults={
                        "location": marriage_place or "",
                        "description": f"Брак с {related.full_name_display}",
                        "created_by": self.request.user,
                    },
                )

            messages.success(self.request, f'Супруг(а) "{person.full_name_display}" успешно создан(а).')
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
        has_exact_duplicate = form.exact_duplicate is not None
        has_similar_duplicates = len(form.duplicates_found) > 0

        if (has_exact_duplicate or has_similar_duplicates) and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["exact_duplicate"] = form.exact_duplicate
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(context)

        response = super().form_valid(form)

        # === ЛОГИРОВАНИЕ: редактирование персоны ===
        from genealogy.utils.audit import get_client_ip, log_action

        log_action(
            tree=self.tree,
            user=self.request.user,
            action="UPDATE",
            entity_type="PERSON",
            entity_id=self.object.pk,
            entity_name=self.object.full_name_display,
            ip_address=get_client_ip(self.request),
        )

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

        # === ЛОГИРОВАНИЕ: удаление персоны ===
        from genealogy.utils.audit import get_client_ip, log_action

        log_action(
            tree=self.tree,
            user=request.user,
            action="DELETE",
            entity_type="PERSON",
            entity_id=self.object.pk,
            entity_name=self.object.full_name_display,
            ip_address=get_client_ip(request),
        )

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

    def get_queryset(self):
        return Person.objects.select_related("tree").prefetch_related(
            "relationships_from", "relationships_to", "life_events", "photos"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        tree = person.tree

        # 1. ГЛАВНОЕ ФОТО
        context["primary_photo"] = person.photos.filter(is_primary=True).first() or person.photos.first()

        # 2. Базовые данные и права
        context["tree"] = tree
        context["combined_timeline"] = person.get_combined_timeline()
        context["can_edit"] = tree.user_can_edit(self.request.user)

        # 3. Роль пользователя
        collaborator = tree.collaborators.filter(user=self.request.user).first()
        context["user_role"] = (
            collaborator.get_role_display()
            if collaborator
            else ("Администратор" if self.request.user.is_superuser else "Гость")
        )

        close_relatives = []
        context["father"] = None
        context["mother"] = None

        # Мы используем уже предвыбранные (prefetched) связи.
        # Это гарантирует, что мы работаем с реальными объектами Person, а не словарями.

        # === 1. РОДИТЕЛИ (текущая персона - это 'to_person', родитель - 'from_person') ===
        for rel in person.relationships_to.all():
            if rel.relationship_type in [
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]:
                parent = rel.from_person
                if not parent:
                    continue

                gender = parent.gender
                if rel.relationship_type == RelationshipTypeEnum.BIOLOGICAL_PARENT:
                    rel_type = "Отец (Родной)" if gender == "male" else "Мать (Родная)"
                elif rel.relationship_type == RelationshipTypeEnum.ADOPTIVE_PARENT:
                    rel_type = "Отец (Приемный)" if gender == "male" else "Мать (Приемная)"
                else:
                    rel_type = "Отчим" if gender == "male" else "Мачеха"

                close_relatives.append({"person": parent, "relation": rel_type})
                if gender == "male":
                    context["father"] = parent
                else:
                    context["mother"] = parent

        # === 2. ДЕТИ (текущая персона - это 'from_person', ребенок - 'to_person') ===
        for rel in person.relationships_from.all():
            if rel.relationship_type in [
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
            ]:
                child = rel.to_person
                if not child:
                    continue
                gender = child.gender
                rel_type = "Сын" if gender == "male" else "Дочь"
                close_relatives.append({"person": child, "relation": rel_type})

        # === 3. СУПРУГИ (могут быть и в from, и в to) ===
        added_spouse_ids = set()  # Чтобы избежать дубликатов

        for rel in person.relationships_from.all():
            if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
                spouse = rel.to_person
                if spouse and spouse.pk not in added_spouse_ids:
                    # Проверяем, есть ли дата окончания (развод)
                    if rel.end_date:
                        rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                    else:
                        rel_type = "Жена" if spouse.gender == "female" else "Муж"
                    close_relatives.append({"person": spouse, "relation": rel_type})
                    added_spouse_ids.add(spouse.pk)

        for rel in person.relationships_to.all():
            if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
                spouse = rel.from_person
                if spouse and spouse.pk not in added_spouse_ids:
                    # Проверяем, есть ли дата окончания (развод)
                    if rel.end_date:
                        rel_type = "Бывшая жена" if spouse.gender == "female" else "Бывший муж"
                    else:
                        rel_type = "Жена" if spouse.gender == "female" else "Муж"
                    close_relatives.append({"person": spouse, "relation": rel_type})
                    added_spouse_ids.add(spouse.pk)

        # === 4. БРАТЬЯ И СЕСТРЫ (те, у кого есть общий родитель с текущей персоной) ===
        sibling_ids = set()
        for rel in person.relationships_to.all():
            if rel.relationship_type in [
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
            ]:
                parent = rel.from_person
                # Находим всех других детей этого же родителя
                for child_rel in parent.relationships_from.all():
                    if child_rel.relationship_type in [
                        RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        RelationshipTypeEnum.ADOPTIVE_PARENT,
                    ]:
                        sibling = child_rel.to_person
                        if sibling and sibling.pk != person.pk and sibling.pk not in sibling_ids:
                            sibling_ids.add(sibling.pk)
                            rel_type = "Брат" if sibling.gender == "male" else "Сестра"
                            close_relatives.append({"person": sibling, "relation": rel_type})

        context["close_relatives"] = close_relatives

        return context


class LinkRelativeView(LoginRequiredMixin, View):
    """Выбор существующей персоны в качестве родственника."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs["tree_pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления связей в это дерево")

        self.parent1_id = request.GET.get("parent1_id")
        self.relation = request.GET.get("relation")
        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        available_persons = Person.objects.filter(tree=self.tree)

        if self.parent1:
            available_persons = available_persons.exclude(pk=self.parent1.pk)

            if self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
                existing_children = self.parent1.get_children()
                available_persons = available_persons.exclude(pk__in=existing_children.values_list("pk", flat=True))
            elif self.relation in ["father", "mother"]:
                existing_parents = self.parent1.get_parents()
                available_persons = available_persons.exclude(pk__in=existing_parents.values_list("pk", flat=True))
            elif self.relation == "spouse":
                existing_spouses = [s["person"] for s in self.parent1.get_spouses()]
                available_persons = available_persons.exclude(pk__in=[s.pk for s in existing_spouses])

        context = {
            "tree": self.tree,
            "parent1": self.parent1,
            "relation": self.relation,
            "available_persons": available_persons.order_by("last_name", "first_name"),
            "action": f"Выбор {RELATION_LABELS.get(self.relation, 'родственника')}",
        }

        return render(request, "genealogy/link_relative.html", context)

    def post(self, request, *args, **kwargs):
        selected_person_id = request.POST.get("selected_person")

        if not selected_person_id:
            messages.error(request, "Не выбрана персона")
            return redirect(request.get_full_path())

        selected_person = get_object_or_404(Person, pk=selected_person_id)

        if self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            is_biological = self.relation in ["son", "daughter"]
            rel_type = RelationshipTypeEnum.BIOLOGICAL_PARENT if is_biological else RelationshipTypeEnum.ADOPTIVE_PARENT

            Relationship.objects.get_or_create(
                from_person=self.parent1,
                to_person=selected_person,
                relationship_type=rel_type,
                defaults={"created_by": request.user},
            )

            spouse = _get_current_spouse(self.parent1)
            if spouse:
                Relationship.objects.get_or_create(
                    from_person=spouse,
                    to_person=selected_person,
                    relationship_type=rel_type,
                    defaults={"created_by": request.user},
                )

            messages.success(
                request,
                f'Персона "{selected_person.full_name_display}" успешно добавлена как {RELATION_LABELS.get(self.relation, "родственник")}.',
            )

        elif self.relation in ["father", "mother"]:
            Relationship.objects.get_or_create(
                from_person=selected_person,
                to_person=self.parent1,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={"created_by": request.user},
            )
            messages.success(
                request,
                f'Персона "{selected_person.full_name_display}" успешно добавлена как {RELATION_LABELS.get(self.relation, "родственник")}.',
            )

        elif self.relation == "spouse":
            Relationship.objects.get_or_create(
                from_person=self.parent1,
                to_person=selected_person,
                relationship_type=RelationshipTypeEnum.SPOUSE,
                defaults={"created_by": request.user, "is_current": True},
            )
            messages.success(request, f'Персона "{selected_person.full_name_display}" успешно добавлена как супруг(а).')

        return redirect("genealogy:person_detail", pk=self.parent1.pk)


class PersonPhotoUploadView(LoginRequiredMixin, View):
    """Загрузка новой фотографии для персоны."""

    def post(self, request, person_pk):
        person = get_object_or_404(Person, pk=person_pk)
        if not person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для добавления фотографий.")
            return redirect("genealogy:person_detail", pk=person_pk)

        image = request.FILES.get("photo")
        caption = request.POST.get("caption", "").strip()
        is_primary = request.POST.get("is_primary") == "on"

        if not image:
            messages.error(request, "Пожалуйста, выберите файл изображения.")
            return redirect("genealogy:person_detail", pk=person_pk)

        # Если это главное фото, обновляем аватар персоны
        if is_primary:
            person.photo = image
            person.save()

        # Создаём запись в галерее

        PersonPhoto.objects.create(person=person, image=image, caption=caption, is_primary=is_primary)
        # Создаём запись в галерее
        photo = PersonPhoto.objects.create(person=person, image=image, caption=caption, is_primary=is_primary)

        # === ЛОГИРОВАНИЕ: загрузка фото ===
        from genealogy.utils.audit import get_client_ip, log_action

        log_action(
            tree=person.tree,
            user=request.user,
            action="CREATE",
            entity_type="PHOTO",
            entity_id=photo.pk,
            entity_name=f"Фото для {person.full_name_display}",
            ip_address=get_client_ip(request),
        )

        messages.success(request, "Фотография успешно добавлена.")
        return redirect("genealogy:person_detail", pk=person_pk)
        messages.success(request, "Фотография успешно добавлена.")
        return redirect("genealogy:person_detail", pk=person_pk)


class PersonPhotoDeleteView(LoginRequiredMixin, View):
    """Удаление фотографии из галереи."""

    def post(self, request, photo_pk):
        from genealogy.models import PersonPhoto

        photo = get_object_or_404(PersonPhoto, pk=photo_pk)

        if not photo.person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для удаления фотографий.")
            return redirect("genealogy:person_detail", pk=photo.person.pk)

        person_pk = photo.person.pk

        # Если удаляем главное фото, очищаем аватар
        if photo.is_primary:
            photo.person.photo = None
            photo.person.save()

        # Удаляем файл с диска
        if photo.image:
            photo.image.delete(save=False)

        # === ЛОГИРОВАНИЕ: удаление фото ===
        from genealogy.utils.audit import get_client_ip, log_action

        log_action(
            tree=photo.person.tree,
            user=request.user,
            action="DELETE",
            entity_type="PHOTO",
            entity_id=photo.pk,
            entity_name=f"Фото {photo.person.full_name_display}",
            ip_address=get_client_ip(request),
        )

        # Удаляем файл с диска
        if photo.image:
            photo.image.delete(save=False)

        photo.delete()
        photo.delete()
        messages.success(request, "Фотография удалена.")
        return redirect("genealogy:person_detail", pk=person_pk)


class PersonPhotoSetPrimaryView(LoginRequiredMixin, View):
    """Установка фотографии как главной (аватар)."""

    def post(self, request, photo_pk):
        from genealogy.models import PersonPhoto

        photo = get_object_or_404(PersonPhoto, pk=photo_pk)

        if not photo.person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для изменения фотографий.")
            return redirect("genealogy:person_detail", pk=photo.person.pk)

        # Сбрасываем все другие фото как неглавные
        PersonPhoto.objects.filter(person=photo.person).update(is_primary=False)

        # Устанавливаем текущее как главное
        photo.is_primary = True
        photo.save()

        # Обновляем аватар персоны
        photo.person.photo = photo.image
        photo.person.save()

        messages.success(request, "Фотография установлена как главная.")
        return redirect("genealogy:person_detail", pk=photo.person.pk)
